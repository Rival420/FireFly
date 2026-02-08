"""
Enrichment pipeline — orchestrates post-discovery deep enumeration.

Architecture (SOLID):
- Single Responsibility: Each enricher does exactly one job.
- Open/Closed: Add enrichers via register() without touching pipeline code.
- Liskov: Every enricher satisfies the Enricher protocol.
- Interface Segregation: Enricher protocol is minimal (can_enrich + enrich).
- Dependency Inversion: Pipeline depends on the Enricher abstraction.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

logger = logging.getLogger("firefly")


# ---------------------------------------------------------------------------
# Internal device representation used throughout the pipeline
# ---------------------------------------------------------------------------
@dataclass
class DeviceInfo:
    """Mutable device record accumulated through enrichment stages."""

    protocol: str = ""
    address: str = ""
    port: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Enriched identity
    friendly_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    serial_number: str | None = None
    device_url: str | None = None

    # Classification
    device_category: str | None = None
    device_tags: list[str] = field(default_factory=list)

    # OS fingerprint
    os_guess: str | None = None

    # Services & banners
    services: list[dict[str, Any]] = field(default_factory=list)
    banners: dict[int, str] = field(default_factory=dict)

    # Errors accumulated during enrichment (non-fatal)
    enrichment_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Enricher protocol — every stage must satisfy this
# ---------------------------------------------------------------------------
@runtime_checkable
class Enricher(Protocol):
    """Minimal interface for enrichment stages."""

    name: str

    def can_enrich(self, device: DeviceInfo) -> bool: ...

    def enrich(self, device: DeviceInfo, timeout: float) -> DeviceInfo: ...


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------
class EnrichmentPipeline:
    """Runs registered enrichers against discovered devices (thread-pooled)."""

    def __init__(self, max_workers: int = 10) -> None:
        self._enrichers: list[Enricher] = []
        self._max_workers = max_workers

    def register(self, enricher: Enricher) -> "EnrichmentPipeline":
        self._enrichers.append(enricher)
        return self

    # -- Single device ---------------------------------------------------
    def enrich_device(self, device: DeviceInfo, timeout: float) -> DeviceInfo:
        for enricher in self._enrichers:
            try:
                if enricher.can_enrich(device):
                    device = enricher.enrich(device, timeout)
            except Exception as exc:
                device.enrichment_errors.append(f"{enricher.name}: {exc}")
                logger.debug("Enricher %s failed for %s: %s", enricher.name, device.address, exc)
        return device

    # -- Batch (parallel) ------------------------------------------------
    def enrich_all(self, devices: list[DeviceInfo], timeout: float) -> list[DeviceInfo]:
        if not devices:
            return devices
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(self.enrich_device, dev, timeout): idx
                for idx, dev in enumerate(devices)
            }
            results: list[DeviceInfo | None] = [None] * len(devices)
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    results[idx] = devices[idx]
        return [r for r in results if r is not None]


# ===================================================================
# Protocol-specific enrichers (kept here — tightly coupled to schemas)
# ===================================================================

class UPnPDeepEnricher:
    """Fetch UPnP device-description XML and extract detailed metadata.

    Reuses the same SSRF guardrails as upnp.py (http/https only, private IPs,
    no redirects, size cap, defusedxml).
    """

    name = "upnp_deep"

    def can_enrich(self, device: DeviceInfo) -> bool:
        return device.protocol == "upnp" and bool(device.raw_data.get("LOCATION"))

    def enrich(self, device: DeviceInfo, timeout: float) -> DeviceInfo:
        import requests
        from defusedxml import ElementTree as ET

        location = device.raw_data.get("LOCATION", "")
        if not location:
            return device

        # ---- SSRF guard (same rules as upnp.py) ----
        parsed = urlparse(location)
        if parsed.scheme not in ("http", "https"):
            return device
        host = parsed.hostname
        if not host:
            return device
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            try:
                ip = ipaddress.ip_address(socket.gethostbyname(host))
            except Exception:
                return device
        if not (ip.is_private or ip.is_link_local or ip.is_loopback):
            return device

        # ---- Fetch XML ----
        try:
            session = requests.Session()
            session.trust_env = False
            resp = session.get(
                location,
                timeout=min(timeout, 3.0),
                allow_redirects=False,
                headers={"User-Agent": "FireFly/1.0"},
                stream=True,
            )
            if resp.status_code != 200:
                return device
            ct = (resp.headers.get("Content-Type") or "").lower()
            if "xml" not in ct:
                return device

            max_bytes = 1024 * 1024
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                total += len(chunk)
                if total > max_bytes:
                    return device
                chunks.append(chunk)

            xml_text = b"".join(chunks).decode("utf-8", errors="replace")
            root = ET.fromstring(xml_text)

            # Detect namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            dev_node = root.find(f".//{ns}device")
            if dev_node is None:
                return device

            def _text(tag: str) -> str | None:
                el = dev_node.find(f"{ns}{tag}")  # type: ignore[union-attr]
                return el.text.strip() if el is not None and el.text else None

            device.friendly_name = device.friendly_name or _text("friendlyName")
            device.manufacturer = _text("manufacturer")
            model_name = _text("modelName")
            model_number = _text("modelNumber")
            device.model = model_name or model_number
            fw = _text("firmwareVersion")
            if fw:
                device.firmware_version = fw
            elif model_number and model_name:
                device.firmware_version = model_number
            device.serial_number = _text("serialNumber") or _text("UDN")
            device.device_url = (
                _text("presentationURL") or _text("URLBase") or location
            )

            # Extract service list
            svc_list = dev_node.find(f"{ns}serviceList")  # type: ignore[union-attr]
            if svc_list is not None:
                for svc in svc_list.findall(f"{ns}service"):
                    svc_type = svc.findtext(f"{ns}serviceType", "")
                    if svc_type:
                        short_name = svc_type.split(":")[-2] if ":" in svc_type else svc_type
                        device.services.append({
                            "port": parsed.port or (443 if parsed.scheme == "https" else 80),
                            "name": short_name,
                            "banner": svc_type,
                            "tls": parsed.scheme == "https",
                        })
        except Exception as exc:
            device.enrichment_errors.append(f"upnp_deep: {exc}")

        return device


class MDNSTxtEnricher:
    """Extract manufacturer, model, firmware from mDNS TXT records."""

    name = "mdns_txt"

    def can_enrich(self, device: DeviceInfo) -> bool:
        return device.protocol == "mdns"

    def enrich(self, device: DeviceInfo, timeout: float) -> DeviceInfo:
        props = device.raw_data.get("properties") or {}
        if not props:
            return device

        txt: dict[str, str] = {}
        for k, v in props.items():
            key = k.decode("utf-8", errors="replace") if isinstance(k, bytes) else str(k)
            val = v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)
            txt[key.lower()] = val

        device.manufacturer = (
            txt.get("manufacturer") or txt.get("usb_mfg") or txt.get("vendor")
            or device.manufacturer
        )
        device.model = (
            txt.get("ty") or txt.get("model") or txt.get("product")
            or txt.get("usb_mdl") or device.model
        )
        device.firmware_version = (
            txt.get("fv") or txt.get("firmware") or txt.get("sw")
            or txt.get("txtvers") or device.firmware_version
        )
        device.serial_number = (
            txt.get("serialnumber") or txt.get("sn") or device.serial_number
        )
        device.device_url = txt.get("adminurl") or txt.get("url") or device.device_url
        return device


class WSDMetadataEnricher:
    """Parse WS-Discovery SOAP response XML for device metadata."""

    name = "wsd_metadata"

    def can_enrich(self, device: DeviceInfo) -> bool:
        return device.protocol == "wsd" and bool(device.raw_data.get("response"))

    def enrich(self, device: DeviceInfo, timeout: float) -> DeviceInfo:
        from defusedxml import ElementTree as ET

        xml = device.raw_data.get("response", "")
        if not xml:
            return device
        try:
            root = ET.fromstring(xml)
            ns = {
                "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
                "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
            }

            types_el = root.find(".//d:Types", ns)
            if types_el is not None and types_el.text:
                device.friendly_name = device.friendly_name or types_el.text.strip()

            scopes_el = root.find(".//d:Scopes", ns)
            if scopes_el is not None and scopes_el.text:
                _parse_wsd_scopes(device, scopes_el.text.strip())

            xaddrs_el = root.find(".//d:XAddrs", ns)
            if xaddrs_el is not None and xaddrs_el.text:
                device.device_url = xaddrs_el.text.strip().split()[0]
        except Exception as exc:
            device.enrichment_errors.append(f"wsd_metadata: {exc}")

        return device


def _parse_wsd_scopes(device: DeviceInfo, scopes: str) -> None:
    """Extract structured metadata from WSD/ONVIF scope URIs."""
    for scope in scopes.split():
        lower = scope.lower()
        if "onvif.org/name/" in lower:
            device.friendly_name = scope.split("/name/")[-1].replace("%20", " ")
        elif "onvif.org/hardware/" in lower:
            device.model = scope.split("/hardware/")[-1].replace("%20", " ")
        elif "onvif.org/type/" in lower:
            tag = scope.split("/type/")[-1]
            if tag and tag not in device.device_tags:
                device.device_tags.append(tag)


class MQTTBrokerEnricher:
    """Extract device metadata from MQTT $SYS data and broker identification."""

    name = "mqtt_broker"

    def can_enrich(self, device: DeviceInfo) -> bool:
        return device.protocol == "mqtt"

    def enrich(self, device: DeviceInfo, timeout: float) -> DeviceInfo:
        metadata = device.raw_data.get("metadata", {})

        # Extract broker name/version from $SYS/broker/version
        version_str = metadata.get("$SYS/broker/version", "")
        if version_str:
            lower = version_str.lower()
            if "mosquitto" in lower:
                device.manufacturer = "Eclipse Foundation"
                device.model = "Mosquitto"
            elif "emqx" in lower:
                device.manufacturer = "EMQ Technologies"
                device.model = "EMQX"
            elif "hivemq" in lower:
                device.manufacturer = "HiveMQ GmbH"
                device.model = "HiveMQ"
            elif "vernemq" in lower:
                device.manufacturer = "Erlio GmbH"
                device.model = "VerneMQ"
            elif "rabbitmq" in lower:
                device.manufacturer = "Broadcom"
                device.model = "RabbitMQ"
            device.firmware_version = version_str

        device.friendly_name = device.raw_data.get("broker_name") or device.friendly_name

        # Record the MQTT port as a service
        port = device.port or 1883
        device.services.append({
            "port": port,
            "name": "MQTT",
            "banner": version_str or "",
            "tls": device.raw_data.get("tls_supported", False),
        })

        return device


class CoAPResourceEnricher:
    """Extract device metadata from CoAP resource descriptions."""

    name = "coap_resource"

    def can_enrich(self, device: DeviceInfo) -> bool:
        return device.protocol == "coap"

    def enrich(self, device: DeviceInfo, timeout: float) -> DeviceInfo:
        resources = device.raw_data.get("resources", [])
        for res in resources:
            rt = res.get("rt", "") or ""
            # Map OIC/OCF resource types to device metadata
            if "oic.d." in rt:
                device.device_category = rt.split("oic.d.")[-1]
            elif "oic.wk.d" in rt:
                device.device_category = "ocf-device"

            if res.get("uri") and res.get("observable"):
                device.services.append({
                    "port": device.port or 5683,
                    "name": f"CoAP:{res['uri']}",
                    "banner": f"rt={rt}" if rt else "",
                    "tls": False,
                })

        device.friendly_name = device.raw_data.get("device_type") or device.friendly_name
        return device


# ===================================================================
# Conversion helpers (discovery dicts  ↔  DeviceInfo)
# ===================================================================

def devices_from_results(results: dict[str, list]) -> list[DeviceInfo]:
    """Convert raw discovery result dicts → DeviceInfo objects."""
    devices: list[DeviceInfo] = []

    for raw in results.get("upnp", []):
        devices.append(DeviceInfo(
            protocol="upnp",
            address=raw.get("address", ""),
            raw_data=dict(raw),
            friendly_name=raw.get("name"),
        ))

    for raw in results.get("mdns", []):
        addrs = raw.get("addresses") or []
        devices.append(DeviceInfo(
            protocol="mdns",
            address=addrs[0] if addrs else "",
            port=raw.get("port"),
            raw_data=dict(raw),
            friendly_name=raw.get("name"),
        ))

    for raw in results.get("wsd", []):
        devices.append(DeviceInfo(
            protocol="wsd",
            address=raw.get("address", ""),
            raw_data=dict(raw),
        ))

    for raw in results.get("mqtt", []):
        devices.append(DeviceInfo(
            protocol="mqtt",
            address=raw.get("address", ""),
            port=raw.get("port", 1883),
            raw_data=dict(raw),
            friendly_name=raw.get("broker_name"),
        ))

    for raw in results.get("coap", []):
        devices.append(DeviceInfo(
            protocol="coap",
            address=raw.get("address", ""),
            port=raw.get("port", 5683),
            raw_data=dict(raw),
            friendly_name=raw.get("device_type"),
        ))

    return devices


def fingerprint_dict(dev: DeviceInfo) -> dict[str, Any]:
    """Serialize enrichment fields into a JSON-safe dict."""
    return {
        "manufacturer": dev.manufacturer,
        "model": dev.model,
        "firmware_version": dev.firmware_version,
        "serial_number": dev.serial_number,
        "device_url": dev.device_url,
        "device_category": dev.device_category,
        "device_tags": dev.device_tags,
        "os_guess": dev.os_guess,
        "services": dev.services,
        "banners": {str(k): v for k, v in dev.banners.items()},
    }


def apply_enrichment(results: dict[str, list], enriched: list[DeviceInfo]) -> dict[str, list]:
    """Merge fingerprint data back into the original results dict."""
    counters: dict[str, int] = {"upnp": 0, "mdns": 0, "wsd": 0, "mqtt": 0, "coap": 0}
    for dev in enriched:
        proto = dev.protocol
        idx = counters.get(proto, 0)
        proto_list = results.get(proto, [])
        if idx < len(proto_list):
            proto_list[idx]["fingerprint"] = fingerprint_dict(dev)
        counters[proto] = idx + 1
    return results


# ===================================================================
# Factory — builds the default pipeline with all enrichers
# ===================================================================

def build_default_pipeline() -> EnrichmentPipeline:
    """Assemble the standard enrichment pipeline."""
    from protocols.fingerprint import ServerHeaderFingerprinter
    from protocols.banner import BannerGrabber
    from protocols.taxonomy import DeviceClassifier

    pipeline = EnrichmentPipeline()
    pipeline.register(UPnPDeepEnricher())
    pipeline.register(MDNSTxtEnricher())
    pipeline.register(WSDMetadataEnricher())
    pipeline.register(MQTTBrokerEnricher())
    pipeline.register(CoAPResourceEnricher())
    pipeline.register(ServerHeaderFingerprinter())
    pipeline.register(BannerGrabber())
    pipeline.register(DeviceClassifier())      # must run last
    return pipeline
