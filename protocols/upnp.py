import socket
import time

class UPnPDiscovery:
    MULTICAST_GROUP = ("239.255.255.250", 1900)

    def __init__(self, timeout=5):
        self.timeout = timeout

    def discover(self):
        discovered = []
        message = "\r\n".join([
            "M-SEARCH * HTTP/1.1",
            "HOST:239.255.255.250:1900",
            'MAN:"ssdp:discover"',
            "MX:3",
            "ST:ssdp:all",
            "", ""
        ])
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        try:
            sock.sendto(message.encode("utf-8"), self.MULTICAST_GROUP)
            start = time.time()
            while True:
                try:
                    data, addr = sock.recvfrom(65507)
                    response = data.decode("utf-8", errors="replace")
                    device = self.parse_response(response)
                    device["address"] = addr[0]
                    discovered.append(device)
                except socket.timeout:
                    break
                if time.time() - start > self.timeout:
                    break
        finally:
            sock.close()
        return discovered

    @staticmethod
    def parse_response(response):
        device = {}
        for line in response.split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                device[key.strip().upper()] = value.strip()
        return device
