"""
OS and device fingerprinting from protocol response analysis.

Extracts OS / firmware hints from:
- UPnP SERVER headers
- HTTP Server headers (from banner grabs)
- mDNS TXT records
- Response behavioral patterns
"""

from __future__ import annotations

import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protocols.enrichment import DeviceInfo

logger = logging.getLogger("firefly")


# ---------------------------------------------------------------------------
# Pattern database — maps regex → OS / platform name
# ---------------------------------------------------------------------------
_OS_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Specific distributions / products first
    (re.compile(r"Synology", re.I), "Synology DSM (Linux)"),
    (re.compile(r"QNAP", re.I), "QNAP QTS (Linux)"),
    (re.compile(r"MikroTik", re.I), "MikroTik RouterOS"),
    (re.compile(r"OpenWrt", re.I), "OpenWrt (Linux)"),
    (re.compile(r"DD-WRT", re.I), "DD-WRT (Linux)"),
    (re.compile(r"Ubiquiti|UniFi", re.I), "Ubiquiti (Linux)"),
    (re.compile(r"FreeNAS|TrueNAS", re.I), "TrueNAS (FreeBSD)"),
    (re.compile(r"pfSense", re.I), "pfSense (FreeBSD)"),
    (re.compile(r"ESXi|VMware", re.I), "VMware ESXi"),
    (re.compile(r"Cisco", re.I), "Cisco IOS"),
    (re.compile(r"Roku", re.I), "Roku OS"),
    (re.compile(r"Tizen", re.I), "Samsung Tizen"),
    (re.compile(r"webOS", re.I), "LG webOS"),
    (re.compile(r"Android", re.I), "Android"),
    (re.compile(r"AirPort", re.I), "Apple AirPort"),
    # Generic OS families
    (re.compile(r"Ubuntu", re.I), "Linux (Ubuntu)"),
    (re.compile(r"Debian", re.I), "Linux (Debian)"),
    (re.compile(r"CentOS|Red\s?Hat|RHEL", re.I), "Linux (RHEL)"),
    (re.compile(r"Fedora", re.I), "Linux (Fedora)"),
    (re.compile(r"Arch\s?Linux", re.I), "Linux (Arch)"),
    (re.compile(r"Linux", re.I), "Linux"),
    (re.compile(r"FreeBSD", re.I), "FreeBSD"),
    (re.compile(r"Windows\s*NT\s*10", re.I), "Windows 10/11"),
    (re.compile(r"Windows\s*NT\s*6\.3", re.I), "Windows 8.1"),
    (re.compile(r"Windows\s*NT\s*6\.[12]", re.I), "Windows 7/8"),
    (re.compile(r"Windows", re.I), "Windows"),
    (re.compile(r"Darwin|macOS|Mac\s?OS", re.I), "macOS"),
    (re.compile(r"iPhone\s?OS|iOS", re.I), "iOS"),
]

# Patterns to extract version strings from SERVER headers
_VERSION_RE = re.compile(
    r"(?:UPnP/[\d.]+\s+)?(\S+/[\d.]+)",
    re.I,
)


class ServerHeaderFingerprinter:
    """Extract OS hints from UPnP SERVER header and HTTP banners."""

    name = "server_header_fingerprint"

    def can_enrich(self, device: "DeviceInfo") -> bool:
        return bool(
            device.raw_data.get("SERVER")
            or device.banners
        )

    def enrich(self, device: "DeviceInfo", timeout: float) -> "DeviceInfo":
        candidates: list[str] = []

        # UPnP SERVER header
        server = device.raw_data.get("SERVER", "")
        if server:
            candidates.append(server)

        # HTTP banners may contain Server headers
        for banner_text in device.banners.values():
            for line in banner_text.splitlines():
                if line.lower().startswith("server:"):
                    candidates.append(line.split(":", 1)[1].strip())

        # Try each candidate against the pattern database
        for text in candidates:
            guess = _match_os(text)
            if guess:
                device.os_guess = guess
                break

        return device


def _match_os(text: str) -> str | None:
    """Match text against OS pattern database, return best match or None."""
    for pattern, os_name in _OS_PATTERNS:
        if pattern.search(text):
            return os_name
    return None
