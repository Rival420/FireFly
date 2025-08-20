"""
Module: upnp.py
Purpose: Discover UPnP devices using SSDP and enrich device info by fetching device description XML.
"""

import socket
import time
import logging
from urllib.parse import urlparse
import ipaddress
from defusedxml import ElementTree as ET
import requests  # Make sure to install requests (pip install requests)

logger = logging.getLogger("firefly")

class UPnPDiscovery:
    MULTICAST_GROUP = ("239.255.255.250", 1900)

    def __init__(self, timeout=5, st="ssdp:all", mx=3, multicast_ttl=2, verbose=False, interface_ip=None):
        """
        Initialize the UPnP discovery instance.

        :param timeout: How long (in seconds) to wait for responses.
        :param st: The search target header value. Defaults to "ssdp:all".
        :param mx: The MX header value, indicating the maximum wait time in seconds.
        :param multicast_ttl: Multicast Time-to-Live for the UDP packet.
        :param verbose: If True, enable debug logging.
        """
        self.timeout = timeout
        self.st = st
        self.mx = mx
        self.multicast_ttl = multicast_ttl
        self.verbose = verbose
        self.interface_ip = interface_ip

        if self.verbose:
            logging.basicConfig(level=logging.DEBUG)
            logging.debug("UPnPDiscovery initialized with timeout=%s, st=%s, mx=%s, ttl=%s",
                          timeout, st, mx, multicast_ttl)

    def discover(self):
        """
        Discover UPnP devices by sending an SSDP M-SEARCH request and then enrich their info.

        :return: A list of dictionaries containing the discovered device info.
        """
        discovered = []
        message = "\r\n".join([
            "M-SEARCH * HTTP/1.1",
            f"HOST:{self.MULTICAST_GROUP[0]}:{self.MULTICAST_GROUP[1]}",
            'MAN:"ssdp:discover"',
            f"MX:{self.mx}",
            f"ST:{self.st}",
            "", ""
        ])
        if self.verbose:
            logging.debug("Sending SSDP M-SEARCH message:\n%s", message)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.multicast_ttl)
        # If a specific interface is requested, bind and set multicast interface
        if self.interface_ip:
            try:
                sock.bind((self.interface_ip, 0))
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(self.interface_ip),
                )
            except Exception as bind_err:
                if self.verbose:
                    logging.debug("Failed to bind to interface %s: %s", self.interface_ip, bind_err)

        try:
            sock.sendto(message.encode("utf-8"), self.MULTICAST_GROUP)
            start = time.time()
            while True:
                try:
                    data, addr = sock.recvfrom(65507)
                    response = data.decode("utf-8", errors="replace")
                    if self.verbose:
                        logging.debug("Received response from %s:\n%s", addr[0], response)
                    device = self.parse_response(response)
                    device["address"] = addr[0]
                    # Enrich device info by fetching device description XML (if available)
                    self.enrich_device_info(device)
                    if device not in discovered:
                        discovered.append(device)
                except socket.timeout:
                    if self.verbose:
                        logging.debug("Socket timeout reached, stopping discovery.")
                    break
                if time.time() - start > self.timeout:
                    if self.verbose:
                        logging.debug("Overall timeout reached, ending discovery loop.")
                    break
        finally:
            sock.close()

        if self.verbose:
            logging.debug("Discovery complete, found %d device(s).", len(discovered))
        return discovered

    @staticmethod
    def parse_response(response):
        """
        Parse an HTTP-like SSDP response into a dictionary.
        :param response: The raw response string from an SSDP device.
        :return: A dictionary of response headers.
        """
        device = {}
        for line in response.split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                device[key.strip().upper()] = value.strip()
        return device

    def enrich_device_info(self, device):
        """
        If the device dictionary contains a LOCATION header, fetch the XML description and update the dictionary.
        Adds 'name' (from <friendlyName>) and 'type' (from <deviceType>) if available.
        :param device: The device dictionary from the SSDP response.
        """
        location = device.get("LOCATION")
        if not location:
            return

        # Basic SSRF protections: only fetch http/https, and only to private or link-local targets.
        try:
            parsed = urlparse(location)
            if parsed.scheme not in ("http", "https"):
                return
            host = parsed.hostname
            if not host:
                return
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                # Resolve hostname to IP
                try:
                    resolved = socket.gethostbyname(host)
                    ip = ipaddress.ip_address(resolved)
                except Exception:
                    return

            if not (ip.is_private or ip.is_link_local or ip.is_loopback):
                return

            session = requests.Session()
            session.trust_env = False  # ignore proxies
            response = session.get(location, timeout=3, allow_redirects=False)
            if response.status_code == 200:
                xml_content = response.text
                root = ET.fromstring(xml_content)
                # Look for the device node (assumes standard UPnP device description)
                device_node = root.find('.//device')
                if device_node is not None:
                    friendlyName = device_node.findtext('friendlyName')
                    deviceType = device_node.findtext('deviceType')
                    if friendlyName:
                        device['name'] = friendlyName
                    if deviceType:
                        device['type'] = deviceType
            else:
                if self.verbose:
                    logging.debug("Failed to fetch XML from LOCATION (%s). HTTP status: %s", location, response.status_code)
        except Exception as e:
            if self.verbose:
                logging.debug("Error fetching/parsing XML from LOCATION (%s): %s", location, e)
