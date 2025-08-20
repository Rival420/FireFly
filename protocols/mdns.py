"""
Module: mdns.py
Purpose: Discover mDNS services using the Zeroconf library.
"""

import socket
import time
import logging

try:
    from zeroconf import Zeroconf, ServiceBrowser, BadTypeInNameException
except ImportError:
    print("[!] Zeroconf library not found. Please install it via: pip install zeroconf")
    raise

logger = logging.getLogger("firefly")


class MDNSDiscovery:
    def __init__(self, timeout=5, service_type="_services._dns-sd._udp.local.", interface_ip=None):
        """
        Initialize the mDNS discovery instance.
        
        :param timeout: How long (in seconds) to wait for responses.
        :param service_type: The mDNS service type to query (e.g. "_http._tcp.local.").
                             Use "All" in your main application to iterate over a list of services.
        """
        self.timeout = timeout
        self.service_type = service_type
        self.interface_ip = interface_ip

    class MDNSListener:
        def __init__(self):
            self.services = {}

        def add_service(self, zeroconf, service_type, name):
            # If we're browsing the meta-service type, simply record the service name
            if service_type == "_services._dns-sd._udp.local.":
                self.services[name] = {"name": name, "type": service_type}
                return

            try:
                info = zeroconf.get_service_info(service_type, name)
            except Exception as e:
                logger.debug(f"[MDNS] Error fetching service info for {name} ({service_type}): {e}")
                info = None

            if info:
                service_data = {
                    "name": name,
                    "type": service_type,
                    "addresses": [socket.inet_ntoa(addr) for addr in info.addresses] if info.addresses else [],
                    "port": info.port,
                    "properties": info.properties
                }
                self.services[name] = service_data
            else:
                self.services[name] = {"name": name, "type": service_type}

        def remove_service(self, zeroconf, service_type, name):
            if name in self.services:
                del self.services[name]

        def update_service(self, zeroconf, service_type, name):
            # Similar check in update_service
            if service_type == "_services._dns-sd._udp.local.":
                self.services[name] = {"name": name, "type": service_type}
                return

            try:
                info = zeroconf.get_service_info(service_type, name)
            except Exception as e:
                logger.debug(f"[MDNS] Error updating service info for {name}: {e}")
                info = None

            if info:
                service_data = {
                    "name": name,
                    "type": service_type,
                    "addresses": [socket.inet_ntoa(addr) for addr in info.addresses] if info.addresses else [],
                    "port": info.port,
                    "properties": info.properties
                }
                self.services[name] = service_data
            else:
                # If we can't fetch updated info keep a minimal record so the
                # service doesn't disappear from the results
                self.services[name] = {"name": name, "type": service_type}

    def discover(self):
        """
        Discover mDNS services of the specified type.
        
        :return: A list of dictionaries containing discovered service information.
        """
        discovered = []
        try:
            if self.interface_ip:
                zeroconf = Zeroconf(interfaces=[self.interface_ip])
            else:
                zeroconf = Zeroconf()
        except Exception as e:
            logger.debug("Failed to initialize Zeroconf: %s", e)
            return discovered
        listener = self.MDNSListener()

        try:
            browser = ServiceBrowser(zeroconf, self.service_type, listener)
        except BadTypeInNameException as e:
            print(f"[MDNS] Bad service type provided ({self.service_type}): {e}")
            zeroconf.close()
            return discovered

        # Wait for services to be discovered.
        time.sleep(self.timeout)
        try:
            zeroconf.close()
        except Exception:
            pass

        # Collect discovered service data.
        for service in listener.services.values():
            discovered.append(service)
        return discovered
