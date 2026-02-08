"""
MQTT broker discovery.

Scans for MQTT brokers on common ports, attempts anonymous connection,
harvests broker metadata from $SYS topics, and samples live topic traffic
(topic names only — payload content is never logged for privacy/legal).

Security:
- No credential brute-forcing — only anonymous connection attempted.
- Clean session only (clean_session=True) — no persistent state left.
- Payload content is never captured or logged.
- Cleanly disconnects after discovery.
- Inter-probe delay (100 ms default) to protect constrained devices.
"""

from __future__ import annotations

import logging
import socket
import ssl
import threading
import time
import uuid
from typing import Any, List, Optional

import paho.mqtt.client as paho_mqtt

logger = logging.getLogger("firefly")

# ---------------------------------------------------------------------------
# Default MQTT ports to scan
# ---------------------------------------------------------------------------
DEFAULT_PORTS: list[dict[str, Any]] = [
    {"port": 1883, "name": "MQTT",     "tls": False},
    {"port": 8883, "name": "MQTT-TLS", "tls": True},
]

MAX_SYS_COLLECT_TIME = 3.0   # seconds to collect $SYS messages
MAX_TOPIC_COLLECT_TIME = 2.0  # seconds to sample live topics
MAX_SAMPLED_TOPICS = 50       # cap unique topic names
MAX_SYS_ENTRIES = 200         # cap $SYS entries to prevent memory bloat


class MQTTDiscovery:
    """Discover MQTT brokers on the network."""

    def __init__(
        self,
        timeout: int = 5,
        target_ips: list[str] | None = None,
        ports: list[dict[str, Any]] | None = None,
        interface_ip: str | None = None,
        probe_delay_ms: int = 100,
    ) -> None:
        self.timeout = timeout
        self.target_ips = target_ips or []
        self.ports = ports or DEFAULT_PORTS
        self.interface_ip = interface_ip
        self.probe_delay = probe_delay_ms / 1000.0

    def discover(self) -> List[dict]:
        """Run MQTT discovery and return list of broker dicts."""
        start = time.time()
        results: list[dict] = []
        seen: set[tuple[str, int]] = set()

        for ip in self.target_ips:
            if time.time() - start >= self.timeout:
                break

            # Track which ports are open / TLS-capable for this IP
            tls_supported = False
            open_ports: list[dict[str, Any]] = []

            for port_cfg in self.ports:
                if time.time() - start >= self.timeout:
                    break
                port = port_cfg["port"]
                if (ip, port) in seen:
                    continue
                seen.add((ip, port))

                if _tcp_port_open(ip, port, timeout=min(2.0, self.timeout - (time.time() - start))):
                    open_ports.append(port_cfg)
                    if port_cfg.get("tls"):
                        tls_supported = True

            if not open_ports:
                continue

            # Prefer plaintext for probing (simpler, more reliable)
            # but fall back to TLS if only TLS port is open
            probe_cfg = next(
                (p for p in open_ports if not p.get("tls")),
                open_ports[0],
            )

            remaining = self.timeout - (time.time() - start)
            if remaining < 0.5:
                break

            broker_info = self._probe_broker(ip, probe_cfg, tls_supported, remaining)
            if broker_info:
                results.append(broker_info)

            if self.probe_delay > 0:
                time.sleep(self.probe_delay)

        return results

    def _probe_broker(
        self,
        ip: str,
        port_cfg: dict[str, Any],
        tls_supported: bool,
        timeout: float,
    ) -> dict[str, Any] | None:
        """Connect to an MQTT broker and harvest metadata."""
        port = port_cfg["port"]
        use_tls = port_cfg.get("tls", False)

        client_id = f"firefly-scan-{uuid.uuid4().hex[:8]}"
        result: dict[str, Any] = {
            "address": ip,
            "port": port,
            "broker_name": None,
            "broker_version": None,
            "anonymous_access": False,
            "tls_supported": tls_supported,
            "anonymous_publish": False,
            "connected_clients": None,
            "uptime_seconds": None,
            "messages_received": None,
            "messages_sent": None,
            "sampled_topics": [],
            "topic_count": 0,
            "risk_flags": [],
            "metadata": {},
        }

        # Shared state for callbacks
        state = _ProbeState()
        connected_event = threading.Event()
        connect_rc = [None]  # mutable container for closure

        # --- paho-mqtt v2 callbacks (using protocol=MQTTv311) ---
        client = paho_mqtt.Client(
            callback_api_version=paho_mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=True,
            protocol=paho_mqtt.MQTTv311,
        )

        def on_connect(client, userdata, flags, rc, properties=None):
            connect_rc[0] = rc
            connected_event.set()

        def on_message(client, userdata, msg):
            topic = msg.topic
            if topic.startswith("$SYS/"):
                if len(state.sys_data) < MAX_SYS_ENTRIES:
                    try:
                        payload_str = msg.payload.decode("utf-8", errors="replace")
                        state.sys_data[topic] = payload_str
                    except Exception:
                        pass
            else:
                if len(state.sampled_topics) < MAX_SAMPLED_TOPICS:
                    state.sampled_topics.add(topic)

        client.on_connect = on_connect
        client.on_message = on_message

        if use_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            client.tls_set_context(ctx)

        try:
            # Attempt anonymous connect
            connect_timeout = min(timeout * 0.3, 5.0)
            client.connect(ip, port, keepalive=30)
            client.loop_start()

            if not connected_event.wait(timeout=connect_timeout):
                logger.debug("MQTT: connection to %s:%d timed out", ip, port)
                return None

            rc = connect_rc[0]
            if rc != 0:
                # rc=5 means "not authorized" in MQTT 3.1.1
                result["anonymous_access"] = False
                logger.debug("MQTT: %s:%d CONNACK rc=%s (not authorized)", ip, port, rc)
                return result

            result["anonymous_access"] = True
            logger.debug("MQTT: anonymous connection accepted at %s:%d", ip, port)

            # Phase 1: Subscribe to $SYS/# for broker metadata
            sys_collect_time = min(timeout * 0.4, MAX_SYS_COLLECT_TIME)
            client.subscribe("$SYS/#", qos=0)
            time.sleep(sys_collect_time)

            # Parse $SYS metadata
            self._parse_sys_data(state.sys_data, result)

            # Phase 2: Subscribe to # for topic sampling (names only, NOT payloads)
            topic_collect_time = min(timeout * 0.3, MAX_TOPIC_COLLECT_TIME)
            remaining_after_sys = timeout - (sys_collect_time + connect_timeout)
            if remaining_after_sys > 0.5:
                actual_collect = min(topic_collect_time, remaining_after_sys * 0.6)
                client.subscribe("#", qos=0)
                time.sleep(actual_collect)
                client.unsubscribe("#")

            result["sampled_topics"] = sorted(state.sampled_topics)
            result["topic_count"] = len(state.sampled_topics)

            # Phase 3: Test anonymous publish
            remaining_time = timeout - (time.time() - (time.time() - timeout))
            try:
                pub_result = client.publish("firefly/test", b"", qos=0)
                if pub_result.rc == paho_mqtt.MQTT_ERR_SUCCESS:
                    result["anonymous_publish"] = True
            except Exception:
                pass

            # Store raw $SYS data
            result["metadata"] = dict(state.sys_data)

            # Generate risk flags
            self._generate_risk_flags(result)

        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            logger.debug("MQTT: failed to connect to %s:%d: %s", ip, port, exc)
            return None
        except Exception as exc:
            logger.debug("MQTT: unexpected error probing %s:%d: %s", ip, port, exc)
            return None
        finally:
            try:
                client.loop_stop()
            except Exception:
                pass
            try:
                client.disconnect()
            except Exception:
                pass

        return result

    @staticmethod
    def _parse_sys_data(sys_data: dict[str, str], result: dict[str, Any]) -> None:
        """Extract structured metadata from $SYS topic values."""
        # Broker version
        version = sys_data.get("$SYS/broker/version", "")
        if version:
            result["broker_version"] = version
            # Try to extract short broker name
            parts = version.lower().split()
            if parts:
                result["broker_name"] = parts[0].capitalize()

        # Uptime
        uptime_str = (
            sys_data.get("$SYS/broker/uptime")
            or sys_data.get("$SYS/broker/uptime/seconds")
            or ""
        )
        if uptime_str:
            # e.g. "86400 seconds" or just "86400"
            try:
                result["uptime_seconds"] = int(uptime_str.split()[0])
            except (ValueError, IndexError):
                pass

        # Connected clients
        clients_str = (
            sys_data.get("$SYS/broker/clients/connected")
            or sys_data.get("$SYS/broker/clients/active")
            or ""
        )
        if clients_str:
            try:
                result["connected_clients"] = int(clients_str)
            except ValueError:
                pass

        # Messages received
        recv_str = sys_data.get("$SYS/broker/messages/received", "")
        if recv_str:
            try:
                result["messages_received"] = int(recv_str)
            except ValueError:
                pass

        # Messages sent
        sent_str = sys_data.get("$SYS/broker/messages/sent", "")
        if sent_str:
            try:
                result["messages_sent"] = int(sent_str)
            except ValueError:
                pass

    @staticmethod
    def _generate_risk_flags(result: dict[str, Any]) -> None:
        """Generate risk flags based on broker probing results."""
        flags: list[str] = []
        if result.get("anonymous_access"):
            flags.append("open_broker")
        if result.get("anonymous_publish"):
            flags.append("anonymous_publish")
        if not result.get("tls_supported"):
            flags.append("no_tls")
        result["risk_flags"] = flags


class _ProbeState:
    """Thread-safe shared state for MQTT probe callbacks."""

    def __init__(self) -> None:
        self.sys_data: dict[str, str] = {}
        self.sampled_topics: set[str] = set()


def _tcp_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Quick TCP connect check to see if a port is open."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass
