"""
Module: upnp.py
Purpose: Discover UPnP devices using SSDP.
"""

import socket
import time
import logging

class UPnPDiscovery:
    MULTICAST_GROUP = ("239.255.255.250", 1900)

    def __init__(self, timeout=5, st="ssdp:all", mx=3, multicast_ttl=2, verbose=False):
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

        if self.verbose:
            logging.basicConfig(level=logging.DEBUG)
            logging.debug("UPnPDiscovery initialized with timeout=%s, st=%s, mx=%s, ttl=%s",
                          timeout, st, mx, multicast_ttl)

    def discover(self):
        """
        Discover UPnP devices by sending an SSDP M-SEARCH request.

        :return: A list of dictionaries containing the discovered device info.
        """
        discovered = []
        # Build the SSDP discovery message.
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

        # Create a UDP socket.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.multicast_ttl)

        try:
            # Send the discovery message.
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
                    # Add device if it isn't already in our discovered list.
                    if device not in discovered:
                        discovered.append(device)
                except socket.timeout:
                    if self.verbose:
                        logging.debug("Socket timeout reached, stopping discovery.")
                    break
                # Safety break if the loop runs too long.
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

