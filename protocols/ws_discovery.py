"""
Module: ws_discovery.py
Purpose: Discover devices using the WS-Discovery protocol.
"""

import socket
import time
import uuid
import logging

class WSDiscovery:
    def __init__(self, timeout=5, multicast_ttl=2, interface_ip=None):
        """
        Initialize the WS-Discovery instance.
        
        :param timeout: How long (in seconds) to wait for WS-Discovery responses.
        """
        self.timeout = timeout
        self.multicast_ttl = multicast_ttl
        self.interface_ip = interface_ip

    def discover(self):
        """
        Discover devices using WS-Discovery.
        
        :return: A list of dictionaries, each containing the responding device's IP address
                 and the raw XML response.
        """
        discovered = []
        multicast_group = ("239.255.255.250", 3702)
        message_id = f"uuid:{uuid.uuid4()}"

        # WS-Discovery Probe message in SOAP format.
        ws_probe = f"""<?xml version="1.0" encoding="utf-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <e:Header>
    <w:MessageID>{message_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe/>
  </e:Body>
</e:Envelope>"""

        # Create a UDP socket.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(self.timeout)
        try:
            if self.interface_ip:
                sock.bind((self.interface_ip, 0))
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(self.interface_ip),
                )
            else:
                sock.bind(("", 0))
        except Exception as bind_err:
            logging.getLogger("firefly").debug("WS-Discovery bind failed: %s", bind_err)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.multicast_ttl)

        try:
            # Send the WS-Discovery probe.
            sock.sendto(ws_probe.encode("utf-8"), multicast_group)
            start = time.time()

            # Listen for responses.
            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    response = data.decode("utf-8", errors="replace")
                    discovered.append({
                        "address": addr[0],
                        "response": response
                    })
                except socket.timeout:
                    break
                if time.time() - start > self.timeout:
                    break
        finally:
            sock.close()

        return discovered
