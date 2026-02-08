"""
Module: mdns.py
Purpose: Discover mDNS services using the Zeroconf library.

Supports browsing multiple service types simultaneously with a single
Zeroconf instance so that multicast sockets are only opened/closed once
per scan invocation.  This prevents the rapid create→destroy cycle that
left sockets in TIME_WAIT and broke subsequent scans.
"""

import socket
import time
import logging
from typing import List, Optional, Sequence

try:
    from zeroconf import Zeroconf, ServiceBrowser, BadTypeInNameException
except ImportError:
    print("[!] Zeroconf library not found. Please install it via: pip install zeroconf")
    raise

logger = logging.getLogger("firefly")


class MDNSDiscovery:
    def __init__(
        self,
        timeout: int = 5,
        service_type: str = "_services._dns-sd._udp.local.",
        interface_ip: Optional[str] = None,
    ):
        """
        Initialize the mDNS discovery instance.

        :param timeout: How long (in seconds) to wait for responses.
        :param service_type: Default mDNS service type to query.
        :param interface_ip: Optional interface IP to bind Zeroconf to.
        """
        self.timeout = timeout
        self.service_type = service_type
        self.interface_ip = interface_ip

    # ------------------------------------------------------------------
    # Listener – collects services discovered by one or more browsers
    # ------------------------------------------------------------------
    class MDNSListener:
        def __init__(self) -> None:
            self.services: dict = {}

        def _resolve(self, zeroconf: Zeroconf, service_type: str, name: str) -> dict:
            """Try to resolve full service info; fall back to a minimal record."""
            if service_type == "_services._dns-sd._udp.local.":
                return {"name": name, "type": service_type}

            try:
                info = zeroconf.get_service_info(service_type, name, timeout=3000)
            except Exception as exc:
                logger.debug("[MDNS] Error fetching service info for %s (%s): %s", name, service_type, exc)
                info = None

            if info:
                return {
                    "name": name,
                    "type": service_type,
                    "addresses": [socket.inet_ntoa(addr) for addr in info.addresses] if info.addresses else [],
                    "port": info.port,
                    "properties": info.properties,
                }
            return {"name": name, "type": service_type}

        def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
            self.services[name] = self._resolve(zeroconf, service_type, name)

        def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
            # Don't delete – we want to keep a record of everything that was
            # seen during the scan window so results are stable.
            pass

        def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
            self.services[name] = self._resolve(zeroconf, service_type, name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def discover(self, service_types: Optional[Sequence[str]] = None) -> List[dict]:
        """
        Discover mDNS services.

        :param service_types: Optional list of service types to browse
            simultaneously.  When *None*, ``self.service_type`` is used.
        :return: A list of dictionaries containing discovered service info.
        """
        if service_types is None:
            service_types = [self.service_type]

        discovered: List[dict] = []

        try:
            if self.interface_ip:
                zeroconf = Zeroconf(interfaces=[self.interface_ip])
            else:
                zeroconf = Zeroconf()
        except Exception as exc:
            logger.error("Failed to initialise Zeroconf: %s", exc)
            return discovered

        listener = self.MDNSListener()
        browsers: List[ServiceBrowser] = []

        try:
            for svc_type in service_types:
                try:
                    browsers.append(ServiceBrowser(zeroconf, svc_type, listener))
                except BadTypeInNameException as exc:
                    logger.warning("[MDNS] Bad service type (%s): %s", svc_type, exc)

            # Single sleep for all browsers — they share one Zeroconf instance
            # and discover concurrently.
            time.sleep(self.timeout)
        finally:
            try:
                zeroconf.close()
            except Exception:
                pass

        discovered.extend(listener.services.values())
        return discovered
