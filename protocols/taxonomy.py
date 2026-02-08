"""
Device taxonomy — rule-based classification engine.

Classifies discovered devices into categories (camera, printer, NAS, etc.)
by matching accumulated metadata against a prioritised rule database.

Runs as the *last* enricher so it can consider data from all prior stages
(UPnP XML, mDNS TXT, WSD scopes, banners, OS fingerprints).
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protocols.enrichment import DeviceInfo

logger = logging.getLogger("firefly")


@dataclass
class TaxonomyRule:
    """Single classification rule — higher priority is checked first."""

    category: str
    tags: list[str]
    patterns: list[re.Pattern]
    priority: int = 0


# ===================================================================
# Rule database (most specific → least specific)
# ===================================================================
TAXONOMY_RULES: list[TaxonomyRule] = [
    # --- Cameras / Surveillance ---
    TaxonomyRule(
        category="camera",
        tags=["surveillance", "video", "onvif"],
        patterns=[
            re.compile(
                r"onvif|ipcam|hikvision|dahua|axis|amcrest|reolink|vivotek|foscam"
                r"|camera|webcam|NetworkVideoTransmitter",
                re.I,
            ),
            re.compile(r"\brtsp\b", re.I),
        ],
        priority=10,
    ),
    # --- NAS / Storage ---
    TaxonomyRule(
        category="nas",
        tags=["storage", "file-server"],
        patterns=[
            re.compile(
                r"synology|qnap|nas\b|ReadyNAS|netgear.*(stor|nas)|wd.*my.*cloud"
                r"|drobo|asustor|freenas|truenas",
                re.I,
            ),
            re.compile(r"_smb\._tcp|_afpovertcp\._tcp|_nfs\._tcp", re.I),
        ],
        priority=9,
    ),
    # --- Printers ---
    TaxonomyRule(
        category="printer",
        tags=["printing"],
        patterns=[
            re.compile(r"_ipp\._tcp|_printer\._tcp|_pdl-datastream\._tcp", re.I),
            re.compile(
                r"printer|brother|canon|epson|hp.*jet|lexmark|xerox|ricoh|kyocera"
                r"|sharp.*mx|oki\b",
                re.I,
            ),
        ],
        priority=8,
    ),
    # --- Smart Home Hubs ---
    TaxonomyRule(
        category="smart-home-hub",
        tags=["smart-home", "automation"],
        patterns=[
            re.compile(
                r"home.?assistant|hass\b|hubitat|smartthings|wink|vera|homey"
                r"|openhab|domoticz",
                re.I,
            ),
            re.compile(r"_hap\._tcp|homekit|zigbee.*(gate|bridge|hub)|z-wave", re.I),
        ],
        priority=7,
    ),
    # --- MQTT Brokers ---
    TaxonomyRule(
        category="mqtt-broker",
        tags=["iot", "messaging", "mqtt"],
        patterns=[
            re.compile(
                r"mosquitto|emqx|hivemq|vernemq|rabbitmq.*mqtt|activemq",
                re.I,
            ),
            re.compile(r"mqtt.*broker|broker.*1883", re.I),
        ],
        priority=7,
    ),
    # --- CoAP Devices ---
    TaxonomyRule(
        category="coap-device",
        tags=["iot", "constrained", "coap"],
        patterns=[
            re.compile(r"coap|oic\.|ocf\.|lwm2m|ipso", re.I),
            re.compile(r"contiki|riot-os|zephyr|mbed", re.I),
        ],
        priority=6,
    ),
    # --- Media / Streaming ---
    TaxonomyRule(
        category="media",
        tags=["streaming", "entertainment"],
        patterns=[
            re.compile(
                r"chromecast|roku|apple.*tv|fire.*tv|plex|sonos|kodi|dlna"
                r"|upnp.*media|_airplay|_googlecast",
                re.I,
            ),
            re.compile(r"MediaRenderer|MediaServer|_raop\._tcp", re.I),
        ],
        priority=5,
    ),
    # --- Routers / Network Equipment ---
    TaxonomyRule(
        category="router",
        tags=["networking", "infrastructure"],
        patterns=[
            re.compile(
                r"router|gateway|InternetGatewayDevice|WANIPConnection|WANDevice",
                re.I,
            ),
            re.compile(
                r"mikrotik|ubiquiti|unifi|netgear|tp-link|asus.*rt-|linksys"
                r"|openwrt|dd-wrt|cisco|meraki",
                re.I,
            ),
        ],
        priority=5,
    ),
    # --- Smart Speakers ---
    TaxonomyRule(
        category="smart-speaker",
        tags=["voice-assistant", "smart-home"],
        patterns=[
            re.compile(r"echo|alexa|google.*home|google.*nest|homepod", re.I),
        ],
        priority=4,
    ),
    # --- Industrial / SCADA ---
    TaxonomyRule(
        category="industrial",
        tags=["iot", "scada", "plc"],
        patterns=[
            re.compile(
                r"modbus|bacnet|siemens|schneider|allen.?bradley|plc|scada"
                r"|industrial|rockwell",
                re.I,
            ),
        ],
        priority=4,
    ),
    # --- Smart TVs ---
    TaxonomyRule(
        category="smart-tv",
        tags=["display", "entertainment"],
        patterns=[
            re.compile(
                r"samsung.*tv|lg.*tv|sony.*bravia|vizio|tcl|hisense|roku.*tv"
                r"|android.*tv|webos|tizen",
                re.I,
            ),
            re.compile(r"urn:.*television|urn:.*tv", re.I),
        ],
        priority=3,
    ),
    # --- Generic IoT micro-controllers ---
    TaxonomyRule(
        category="iot-device",
        tags=["iot", "embedded"],
        patterns=[
            re.compile(
                r"esp32|esp8266|arduino|raspberry|tasmota|shelly|tuya|mqtt|zigbee",
                re.I,
            ),
        ],
        priority=2,
    ),
    # --- Workstations / Computers ---
    TaxonomyRule(
        category="computer",
        tags=["workstation"],
        patterns=[
            re.compile(r"_workstation\._tcp|_smb\._tcp.*windows|_rdp\._tcp", re.I),
        ],
        priority=1,
    ),
]


class DeviceClassifier:
    """Classify devices by matching all accumulated metadata against taxonomy rules."""

    name = "device_classifier"

    def __init__(self, rules: list[TaxonomyRule] | None = None) -> None:
        self._rules = sorted(rules or TAXONOMY_RULES, key=lambda r: -r.priority)

    def can_enrich(self, device: "DeviceInfo") -> bool:
        return True  # always attempt classification

    def enrich(self, device: "DeviceInfo", timeout: float) -> "DeviceInfo":
        blob = _build_search_blob(device)

        for rule in self._rules:
            if any(p.search(blob) for p in rule.patterns):
                device.device_category = rule.category
                device.device_tags = list(set(device.device_tags + rule.tags))
                return device

        device.device_category = device.device_category or "unknown"
        return device


def _build_search_blob(device: "DeviceInfo") -> str:
    """Concatenate all device metadata into a single searchable string."""
    parts: list[str] = [
        device.friendly_name or "",
        device.manufacturer or "",
        device.model or "",
        device.firmware_version or "",
        device.os_guess or "",
        str(device.raw_data),
    ]
    for banner in device.banners.values():
        parts.append(banner)
    for svc in device.services:
        parts.append(str(svc))
    for tag in device.device_tags:
        parts.append(tag)
    return " ".join(parts)
