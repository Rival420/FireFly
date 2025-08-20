import logging
import os
from typing import List

from pydantic import BaseModel, Field, ValidationError


class AppSettings(BaseModel):
    allowed_origins: List[str] = Field(default_factory=lambda: _default_allowed_origins())
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    default_timeout_seconds: int = Field(default=int(os.getenv("DEFAULT_TIMEOUT", "5")))
    max_timeout_seconds: int = Field(default=int(os.getenv("MAX_TIMEOUT", "30")))
    upnp_default_st: str = Field(default=os.getenv("UPNP_DEFAULT_ST", "ssdp:all"))
    upnp_default_mx: int = Field(default=int(os.getenv("UPNP_DEFAULT_MX", "3")))
    upnp_default_ttl: int = Field(default=int(os.getenv("UPNP_DEFAULT_TTL", "2")))


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
    ]

