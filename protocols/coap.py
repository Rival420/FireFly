"""
CoAP (Constrained Application Protocol) resource discovery.

Discovers CoAP devices via multicast and unicast probes, parses CoRE Link
Format (RFC 6690) responses, enumerates resources, and fingerprints devices.

Uses raw UDP sockets with manual CoAP message framing (RFC 7252) — no
external CoAP library required, consistent with how UPnP and WS-Discovery
use raw sockets.

Security:
- Only sends GET requests — never PUT/POST/DELETE.
- Only probes private/link-local/loopback addresses.
- Inter-probe delay (100 ms default) to protect constrained IoT devices.
- Payload content is not logged; only resource URIs and content types.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import random
import re
import socket
import struct
import time
from typing import Any, List, Optional

logger = logging.getLogger("firefly")

# ---------------------------------------------------------------------------
# CoAP constants (RFC 7252)
# ---------------------------------------------------------------------------
COAP_VERSION = 1

TYPE_CON = 0  # Confirmable
TYPE_NON = 1  # Non-confirmable
TYPE_ACK = 2
TYPE_RST = 3

# Method codes (class.detail)
CODE_GET = (0, 1)  # 0.01

# Response codes
CODE_CONTENT = (2, 5)     # 2.05 Content
CODE_VALID = (2, 3)       # 2.03 Valid
CODE_BAD_REQUEST = (4, 0)
CODE_NOT_FOUND = (4, 4)
CODE_UNAUTHORIZED = (4, 1)

# Option numbers
OPTION_URI_PATH = 11
OPTION_CONTENT_FORMAT = 12
OPTION_URI_QUERY = 15

# Content formats
CT_LINK_FORMAT = 40   # application/link-format

# Multicast addresses
COAP_MCAST_IPV4 = "224.0.1.187"
COAP_MCAST_IPV6 = "ff02::fd"
COAP_PORT = 5683
COAP_DTLS_PORT = 5684

PAYLOAD_MARKER = 0xFF
MAX_RESOURCES_PER_DEVICE = 10
MAX_RESPONSE_SIZE = 4096


# ---------------------------------------------------------------------------
# CoAP message encoding / decoding helpers
# ---------------------------------------------------------------------------

def _build_coap_request(
    msg_type: int,
    code: tuple[int, int],
    message_id: int,
    token: bytes,
    uri_path: str,
) -> bytes:
    """Build a CoAP request message (RFC 7252).

    Header (4 bytes):
      Ver(2) | Type(2) | TKL(4) | Code(8) | Message ID(16)
    """
    tkl = len(token)
    first_byte = (COAP_VERSION << 6) | (msg_type << 4) | (tkl & 0x0F)
    code_byte = (code[0] << 5) | code[1]
    header = struct.pack("!BBH", first_byte, code_byte, message_id)

    # Token
    msg = header + token

    # URI-Path options — split path into segments, encode each as option
    segments = [s for s in uri_path.strip("/").split("/") if s]
    prev_option = 0
    for seg in segments:
        delta = OPTION_URI_PATH - prev_option
        prev_option = OPTION_URI_PATH
        seg_bytes = seg.encode("utf-8")
        msg += _encode_option(delta, seg_bytes)

    return msg


def _encode_option(delta: int, value: bytes) -> bytes:
    """Encode a single CoAP option (delta + length + value)."""
    length = len(value)

    # Determine extended delta/length fields
    if delta < 13:
        d = delta
        ext_d = b""
    elif delta < 269:
        d = 13
        ext_d = struct.pack("!B", delta - 13)
    else:
        d = 14
        ext_d = struct.pack("!H", delta - 269)

    if length < 13:
        l_ = length
        ext_l = b""
    elif length < 269:
        l_ = 13
        ext_l = struct.pack("!B", length - 13)
    else:
        l_ = 14
        ext_l = struct.pack("!H", length - 269)

    first = (d << 4) | l_
    return struct.pack("!B", first) + ext_d + ext_l + value


def _parse_coap_response(data: bytes) -> dict[str, Any] | None:
    """Parse a CoAP response message. Returns None if malformed."""
    if len(data) < 4:
        return None

    first_byte, code_byte, msg_id = struct.unpack("!BBH", data[:4])
    version = (first_byte >> 6) & 0x03
    msg_type = (first_byte >> 4) & 0x03
    tkl = first_byte & 0x0F

    if version != COAP_VERSION:
        return None

    code_class = (code_byte >> 5) & 0x07
    code_detail = code_byte & 0x1F

    offset = 4
    token = data[offset : offset + tkl]
    offset += tkl

    # Parse options
    options: list[tuple[int, bytes]] = []
    prev_option_num = 0
    while offset < len(data):
        if data[offset] == PAYLOAD_MARKER:
            offset += 1
            break
        opt_byte = data[offset]
        offset += 1
        delta = (opt_byte >> 4) & 0x0F
        length = opt_byte & 0x0F

        if delta == 13:
            delta = data[offset] + 13
            offset += 1
        elif delta == 14:
            delta = struct.unpack("!H", data[offset : offset + 2])[0] + 269
            offset += 2

        if length == 13:
            length = data[offset] + 13
            offset += 1
        elif length == 14:
            length = struct.unpack("!H", data[offset : offset + 2])[0] + 269
            offset += 2

        option_num = prev_option_num + delta
        prev_option_num = option_num
        opt_value = data[offset : offset + length]
        offset += length
        options.append((option_num, opt_value))

    payload = data[offset:] if offset < len(data) else b""

    return {
        "version": version,
        "type": msg_type,
        "code": (code_class, code_detail),
        "message_id": msg_id,
        "token": token,
        "options": options,
        "payload": payload,
    }


def _parse_link_format(payload: str) -> list[dict[str, Any]]:
    """Parse RFC 6690 CoRE Link Format into a list of resource dicts.

    Example input:
        </temp>;rt="temperature";obs;ct=50,</humidity>;rt="humidity"
    """
    resources: list[dict[str, Any]] = []
    if not payload.strip():
        return resources

    # Split on commas that are NOT inside angle brackets or quotes
    entries = re.split(r",(?=\s*<)", payload.strip())

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # Extract URI from <...>
        uri_match = re.match(r"<([^>]+)>", entry)
        if not uri_match:
            continue

        resource: dict[str, Any] = {"uri": uri_match.group(1)}

        # Parse attributes after the URI
        attrs_str = entry[uri_match.end() :]
        for attr_match in re.finditer(r';([^;=]+)(?:=(?:"([^"]*)"|([^;,]*)))?', attrs_str):
            key = attr_match.group(1).strip()
            value = attr_match.group(2) if attr_match.group(2) is not None else attr_match.group(3)
            if value is not None:
                resource[key] = value.strip()
            else:
                # Boolean attribute (e.g., obs)
                resource[key] = True

        resources.append(resource)

    return resources


def _build_ack(message_id: int, token: bytes) -> bytes:
    """Build an empty CoAP ACK for a confirmable message."""
    tkl = len(token)
    first_byte = (COAP_VERSION << 6) | (TYPE_ACK << 4) | (tkl & 0x0F)
    code_byte = 0  # 0.00 Empty
    return struct.pack("!BBH", first_byte, code_byte, message_id) + token


# ---------------------------------------------------------------------------
# CoAP Discovery class
# ---------------------------------------------------------------------------

class CoAPDiscovery:
    """Discover CoAP devices via multicast and unicast resource discovery."""

    def __init__(
        self,
        timeout: int = 5,
        target_ips: list[str] | None = None,
        interface_ip: str | None = None,
        probe_delay_ms: int = 100,
    ) -> None:
        self.timeout = timeout
        self.target_ips = target_ips or []
        self.interface_ip = interface_ip
        self.probe_delay = probe_delay_ms / 1000.0

    def discover(self) -> List[dict]:
        """Run CoAP discovery and return list of device dicts."""
        start = time.time()
        devices_by_ip: dict[str, dict[str, Any]] = {}

        # Phase 1: Multicast discovery
        multicast_time = min(self.timeout * 0.4, 3.0)
        self._multicast_discover(devices_by_ip, multicast_time)

        # Phase 2: Unicast probes on target IPs + multicast responders
        elapsed = time.time() - start
        remaining = self.timeout - elapsed
        if remaining > 0.5:
            all_ips = set(self.target_ips) | set(devices_by_ip.keys())
            self._unicast_discover(devices_by_ip, all_ips, remaining)

        # Phase 3: Resource enumeration on discovered devices
        elapsed = time.time() - start
        remaining = self.timeout - elapsed
        if remaining > 0.5:
            self._enumerate_resources(devices_by_ip, remaining)

        # Phase 4: DTLS port check
        elapsed = time.time() - start
        remaining = self.timeout - elapsed
        if remaining > 0.3:
            self._check_dtls(devices_by_ip, remaining)

        # Build final results
        results: list[dict] = []
        for ip, dev in devices_by_ip.items():
            dev.setdefault("address", ip)
            dev.setdefault("port", COAP_PORT)
            self._generate_risk_flags(dev)
            results.append(dev)

        return results

    def _multicast_discover(
        self, devices: dict[str, dict], timeout: float
    ) -> None:
        """Send multicast CoAP GET for /.well-known/core."""
        msg_id = random.randint(0, 0xFFFF)
        token = os.urandom(4)
        request = _build_coap_request(
            TYPE_NON, CODE_GET, msg_id, token, "/.well-known/core"
        )

        # IPv4 multicast
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("b", 2)
            )
            if self.interface_ip:
                try:
                    sock.setsockopt(
                        socket.IPPROTO_IP,
                        socket.IP_MULTICAST_IF,
                        socket.inet_aton(self.interface_ip),
                    )
                except OSError:
                    logger.debug("CoAP: failed to bind multicast to %s", self.interface_ip)

            sock.settimeout(min(timeout, 1.0))
            sock.sendto(request, (COAP_MCAST_IPV4, COAP_PORT))
            logger.debug("CoAP: sent multicast GET /.well-known/core to %s:%d", COAP_MCAST_IPV4, COAP_PORT)

            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(MAX_RESPONSE_SIZE)
                    source_ip = addr[0]
                    if not _is_safe_ip(source_ip):
                        continue
                    resp = _parse_coap_response(data)
                    if resp and resp["code"] == CODE_CONTENT:
                        payload_str = resp["payload"].decode("utf-8", errors="replace")
                        self._process_wellknown_response(devices, source_ip, payload_str)
                except socket.timeout:
                    continue
                except OSError:
                    break
        except OSError as exc:
            logger.debug("CoAP: IPv4 multicast failed: %s", exc)
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

        # IPv6 multicast (best-effort)
        sock6 = None
        try:
            sock6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock6.setsockopt(
                socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, struct.pack("i", 2)
            )
            sock6.settimeout(min(timeout, 1.0))

            msg_id_v6 = random.randint(0, 0xFFFF)
            token_v6 = os.urandom(4)
            request_v6 = _build_coap_request(
                TYPE_NON, CODE_GET, msg_id_v6, token_v6, "/.well-known/core"
            )
            sock6.sendto(request_v6, (COAP_MCAST_IPV6, COAP_PORT))
            logger.debug("CoAP: sent IPv6 multicast GET /.well-known/core to [%s]:%d", COAP_MCAST_IPV6, COAP_PORT)

            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock6.recvfrom(MAX_RESPONSE_SIZE)
                    source_ip = addr[0]
                    resp = _parse_coap_response(data)
                    if resp and resp["code"] == CODE_CONTENT:
                        payload_str = resp["payload"].decode("utf-8", errors="replace")
                        self._process_wellknown_response(devices, source_ip, payload_str)
                except socket.timeout:
                    continue
                except OSError:
                    break
        except OSError as exc:
            logger.debug("CoAP: IPv6 multicast not available: %s", exc)
        finally:
            if sock6:
                try:
                    sock6.close()
                except OSError:
                    pass

    def _unicast_discover(
        self, devices: dict[str, dict], target_ips: set[str], timeout: float
    ) -> None:
        """Send unicast CoAP GET /.well-known/core to specific IPs."""
        per_host_timeout = min(2.0, timeout / max(len(target_ips), 1))
        start = time.time()

        for ip in target_ips:
            if time.time() - start >= timeout:
                break
            if not _is_safe_ip(ip):
                continue
            # Skip if we already have resources from multicast
            if ip in devices and devices[ip].get("resources"):
                continue

            sock = None
            try:
                msg_id = random.randint(0, 0xFFFF)
                token = os.urandom(4)
                request = _build_coap_request(
                    TYPE_CON, CODE_GET, msg_id, token, "/.well-known/core"
                )

                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(per_host_timeout)
                sock.sendto(request, (ip, COAP_PORT))
                logger.debug("CoAP: unicast GET /.well-known/core to %s:%d", ip, COAP_PORT)

                data, _ = sock.recvfrom(MAX_RESPONSE_SIZE)
                resp = _parse_coap_response(data)
                if resp:
                    # Send ACK for confirmable responses
                    if resp["type"] == TYPE_CON:
                        ack = _build_ack(resp["message_id"], resp["token"])
                        sock.sendto(ack, (ip, COAP_PORT))

                    if resp["code"] == CODE_CONTENT:
                        payload_str = resp["payload"].decode("utf-8", errors="replace")
                        self._process_wellknown_response(devices, ip, payload_str)
                    elif resp["code"] == CODE_UNAUTHORIZED:
                        # Device exists but requires auth
                        if ip not in devices:
                            devices[ip] = {
                                "address": ip,
                                "port": COAP_PORT,
                                "resources": [],
                                "unauthenticated_access": False,
                            }
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass
            finally:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass

            if self.probe_delay > 0:
                time.sleep(self.probe_delay)

    def _enumerate_resources(
        self, devices: dict[str, dict], timeout: float
    ) -> None:
        """GET discovered resource URIs for fingerprinting (content type only)."""
        start = time.time()

        for ip, dev in devices.items():
            resources = dev.get("resources", [])
            if not resources:
                continue

            for res in resources[:MAX_RESOURCES_PER_DEVICE]:
                if time.time() - start >= timeout:
                    return

                uri = res.get("uri", "")
                if not uri or uri == "/.well-known/core":
                    continue

                sock = None
                try:
                    msg_id = random.randint(0, 0xFFFF)
                    token = os.urandom(4)
                    request = _build_coap_request(TYPE_CON, CODE_GET, msg_id, token, uri)

                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(min(2.0, timeout - (time.time() - start)))
                    sock.sendto(request, (ip, COAP_PORT))

                    data, _ = sock.recvfrom(MAX_RESPONSE_SIZE)
                    resp = _parse_coap_response(data)
                    if resp:
                        if resp["type"] == TYPE_CON:
                            ack = _build_ack(resp["message_id"], resp["token"])
                            sock.sendto(ack, (ip, COAP_PORT))

                        # Extract content format from options (don't log payload)
                        for opt_num, opt_val in resp.get("options", []):
                            if opt_num == OPTION_CONTENT_FORMAT and opt_val:
                                ct_value = int.from_bytes(opt_val, "big")
                                res["ct_detected"] = str(ct_value)
                                break

                        # Record payload size for fingerprinting
                        res["payload_size"] = len(resp.get("payload", b""))
                except (socket.timeout, ConnectionRefusedError, OSError):
                    pass
                finally:
                    if sock:
                        try:
                            sock.close()
                        except OSError:
                            pass

                if self.probe_delay > 0:
                    time.sleep(self.probe_delay)

    def _check_dtls(self, devices: dict[str, dict], timeout: float) -> None:
        """Check if DTLS port 5684 is responsive on discovered devices."""
        per_host = min(1.0, timeout / max(len(devices), 1))

        for ip, dev in devices.items():
            sock = None
            try:
                # Send a minimal CoAP request to DTLS port; if anything comes
                # back (even an error) the port is open.
                msg_id = random.randint(0, 0xFFFF)
                token = os.urandom(2)
                probe = _build_coap_request(TYPE_CON, CODE_GET, msg_id, token, "/.well-known/core")

                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(per_host)
                sock.sendto(probe, (ip, COAP_DTLS_PORT))
                data, _ = sock.recvfrom(MAX_RESPONSE_SIZE)
                # Any response (including DTLS alert) means the port is live
                dev["dtls_supported"] = True
            except (socket.timeout, ConnectionRefusedError, OSError):
                dev.setdefault("dtls_supported", False)
            finally:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass

    def _process_wellknown_response(
        self, devices: dict[str, dict], source_ip: str, payload: str
    ) -> None:
        """Parse /.well-known/core response and populate device entry."""
        parsed = _parse_link_format(payload)
        if not parsed:
            return

        dev = devices.setdefault(source_ip, {
            "address": source_ip,
            "port": COAP_PORT,
        })

        resources: list[dict[str, Any]] = []
        observable: list[str] = []
        device_type = None
        firmware = None

        for res in parsed:
            resource_entry: dict[str, Any] = {
                "uri": res.get("uri", ""),
                "rt": res.get("rt"),
                "if_desc": res.get("if"),
                "ct": res.get("ct"),
                "observable": res.get("obs") is not None and res.get("obs") is not False,
                "title": res.get("title"),
            }
            resources.append(resource_entry)

            if resource_entry["observable"]:
                observable.append(resource_entry["uri"])

            # Infer device type from resource types
            rt = res.get("rt", "")
            if rt:
                if "oic.d." in rt:
                    device_type = rt.split("oic.d.")[-1]
                elif "temperature" in rt.lower():
                    device_type = device_type or "sensor"
                elif "light" in rt.lower():
                    device_type = device_type or "light"

        dev["resources"] = resources
        dev["observable_resources"] = observable
        dev["unauthenticated_access"] = True
        dev["device_type"] = device_type
        dev["firmware"] = firmware
        dev["metadata"] = {"raw_link_format": payload}

        logger.debug(
            "CoAP: discovered %d resources on %s (observable: %d)",
            len(resources), source_ip, len(observable),
        )

    @staticmethod
    def _generate_risk_flags(dev: dict) -> None:
        """Generate risk flags based on device data."""
        flags: list[str] = []
        if dev.get("unauthenticated_access"):
            flags.append("unauthenticated_access")
        if not dev.get("dtls_supported", False):
            flags.append("no_dtls")
        if dev.get("observable_resources"):
            flags.append("observable_data_leak")
        dev["risk_flags"] = flags


def _is_safe_ip(ip_str: str) -> bool:
    """Only allow probing private, link-local, or loopback addresses."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_link_local or ip.is_loopback
    except ValueError:
        return False
