import logging
import os
from typing import List

from pydantic import BaseModel, Field, ValidationError


class AppSettings(BaseModel):
    allowed_origins: List[str] = Field(default_factory=lambda: _default_allowed_origins())
    allowed_origin_regex: str | None = Field(
        default=os.getenv(
            "ALLOWED_ORIGIN_REGEX",
            # Allow any private-network / localhost origin so the UI works when
            # accessed via LAN IP (e.g. http://192.168.1.50:3001) without having
            # to enumerate every possible IP in ALLOWED_ORIGINS.
            r"^https?://(localhost|127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$",
        ),
    )
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    default_timeout_seconds: int = Field(default=int(os.getenv("DEFAULT_TIMEOUT", "5")))
    max_timeout_seconds: int = Field(default=int(os.getenv("MAX_TIMEOUT", "30")))
    upnp_default_st: str = Field(default=os.getenv("UPNP_DEFAULT_ST", "ssdp:all"))
    upnp_default_mx: int = Field(default=int(os.getenv("UPNP_DEFAULT_MX", "3")))
    upnp_default_ttl: int = Field(default=int(os.getenv("UPNP_DEFAULT_TTL", "2")))
    api_key: str | None = Field(default=os.getenv("API_KEY"))
    mqtt_default_ports: str = Field(default=os.getenv("MQTT_DEFAULT_PORTS", "1883,8883"))
    mqtt_probe_delay_ms: int = Field(default=int(os.getenv("MQTT_PROBE_DELAY_MS", "100")))
    coap_multicast_enabled: bool = Field(
        default=os.getenv("COAP_MULTICAST_ENABLED", "true").lower() == "true"
    )
    coap_probe_delay_ms: int = Field(default=int(os.getenv("COAP_PROBE_DELAY_MS", "100")))


def get_settings() -> AppSettings:
    try:
        return AppSettings()
    except ValidationError as exc:  # pragma: no cover - defensive
        logging.getLogger("firefly").error("Invalid application settings: %s", exc)
        raise


def _default_allowed_origins() -> List[str]:
    env_value = os.getenv("ALLOWED_ORIGINS")
    if env_value:
        return [origin.strip() for origin in env_value.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]

