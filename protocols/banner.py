"""
Banner grabbing for common IoT service ports.

Connects to discovered devices on well-known ports, sends minimal
protocol-appropriate probes, and captures response banners.

Security:
- Only targets discovered device addresses (no scanning of arbitrary hosts).
- Short timeouts per port (max 2 s) to avoid blocking.
- No authentication probes; read-only banner capture.
- TLS connections do not verify certificates (IoT devices rarely have valid certs).
"""

from __future__ import annotations

import logging
import socket
import ssl
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protocols.enrichment import DeviceInfo

logger = logging.getLogger("firefly")


# ---------------------------------------------------------------------------
# Port database — curated set of common IoT / network service ports
# ---------------------------------------------------------------------------
BANNER_PORTS: dict[int, dict] = {
    21:   {"name": "FTP",       "probe": b"",                                             "tls": False},
    22:   {"name": "SSH",       "probe": b"",                                             "tls": False},
    23:   {"name": "Telnet",    "probe": b"",                                             "tls": False},
    80:   {"name": "HTTP",      "probe": b"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n",      "tls": False},
    443:  {"name": "HTTPS",     "probe": b"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n",      "tls": True},
    554:  {"name": "RTSP",      "probe": b"OPTIONS * RTSP/1.0\r\nCSeq: 1\r\n\r\n",       "tls": False},
    1883: {"name": "MQTT",      "probe": b"",                                             "tls": False},
    8080: {"name": "HTTP-Alt",  "probe": b"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n",      "tls": False},
    8443: {"name": "HTTPS-Alt", "probe": b"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n",      "tls": True},
    8883: {"name": "MQTT-TLS",  "probe": b"",                                             "tls": True},
}

MAX_BANNER_LEN = 512
PER_PORT_TIMEOUT = 2.0


@dataclass
class BannerResult:
    port: int
    service_name: str
    banner: str
    tls: bool = False
    tls_version: str | None = None


class BannerGrabber:
    """Grab banners from common IoT service ports on discovered devices."""

    name = "banner_grabber"

    def __init__(self, ports: dict[int, dict] | None = None) -> None:
        self._ports = ports or BANNER_PORTS

    def can_enrich(self, device: "DeviceInfo") -> bool:
        return bool(device.address)

    def enrich(self, device: "DeviceInfo", timeout: float) -> "DeviceInfo":
        per_port = min(PER_PORT_TIMEOUT, timeout / max(len(self._ports), 1))

        # Also include the device's own port if known and not already in the set
        ports_to_scan = dict(self._ports)
        if device.port and device.port not in ports_to_scan:
            ports_to_scan[device.port] = {
                "name": f"Port-{device.port}",
                "probe": b"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n",
                "tls": False,
            }

        for port, config in ports_to_scan.items():
            result = _grab_single(device.address, port, config, per_port)
            if result:
                device.banners[port] = result.banner
                device.services.append({
                    "port": result.port,
                    "name": result.service_name,
                    "banner": result.banner,
                    "tls": result.tls,
                    "tls_version": result.tls_version,
                })
        return device


def _grab_single(
    host: str,
    port: int,
    config: dict,
    timeout: float,
) -> BannerResult | None:
    """Connect to a single port, optionally send a probe, read the banner."""
    use_tls = config.get("tls", False)
    probe: bytes = config.get("probe", b"")
    service_name: str = config.get("name", f"Port-{port}")

    if isinstance(probe, bytes) and b"{host}" in probe:
        probe = probe.replace(b"{host}", host.encode())

    raw_sock: socket.socket | None = None
    sock: socket.socket | ssl.SSLSocket | None = None
    try:
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(timeout)
        raw_sock.connect((host, port))
        sock = raw_sock

        tls_version: str | None = None
        if use_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw_sock, server_hostname=host)
            tls_version = sock.version()

        if probe:
            sock.sendall(probe)

        banner = sock.recv(1024).decode("utf-8", errors="replace").strip()
        if not banner:
            return None

        if len(banner) > MAX_BANNER_LEN:
            banner = banner[:MAX_BANNER_LEN] + "..."

        return BannerResult(
            port=port,
            service_name=service_name,
            banner=banner,
            tls=use_tls,
            tls_version=tls_version,
        )
    except (socket.timeout, ConnectionRefusedError, ConnectionResetError, OSError):
        return None
    except Exception:
        return None
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass
