from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, constr, conint


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable error message")
    code: Optional[str] = Field(default=None, description="Optional machine-readable error code")


class DiscoverQuery(BaseModel):
    protocol: constr(strip_whitespace=True, to_lower=True) = Field(
        default="all",
        pattern="^(all|upnp|mdns|wsd)$",
        description="Discovery protocol to use",
    )
    timeout: conint(ge=1, le=300) = Field(default=5, description="Timeout in seconds")
    mdns_service: constr(strip_whitespace=True) = Field(
        default="_services._dns-sd._udp.local.", description="mDNS service type or 'all'",
    )
    upnp_st: constr(strip_whitespace=True) = Field(default="ssdp:all")
    upnp_mx: conint(ge=1, le=5) = Field(default=3)
    upnp_ttl: conint(ge=1, le=16) = Field(default=2)
    interface_ip: Optional[str] = Field(default=None, description="Bind to a specific interface IP")
    enrich: bool = Field(default=False, description="Enable deep enumeration and fingerprinting")


# ---------------------------------------------------------------------------
# Fingerprint models (populated when enrich=true)
# ---------------------------------------------------------------------------

class ServiceInfo(BaseModel):
    """A single discovered/enumerated service on a device."""
    port: int
    name: str
    banner: Optional[str] = None
    tls: bool = False
    tls_version: Optional[str] = None


class DeviceFingerprint(BaseModel):
    """Deep enrichment data attached to a discovered device."""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    serial_number: Optional[str] = None
    device_url: Optional[str] = None
    device_category: Optional[str] = None
    device_tags: List[str] = Field(default_factory=list)
    os_guess: Optional[str] = None
    services: List[ServiceInfo] = Field(default_factory=list)
    banners: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-protocol device models
# ---------------------------------------------------------------------------

class UPnPDevice(BaseModel):
    address: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    LOCATION: Optional[str] = None
    USN: Optional[str] = None
    SERVER: Optional[str] = None
    ST: Optional[str] = None
    fingerprint: Optional[DeviceFingerprint] = None


class MDNSService(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    addresses: Optional[List[str]] = None
    port: Optional[int] = None
    properties: Optional[Dict[str, Any]] = None
    fingerprint: Optional[DeviceFingerprint] = None


class WSDDevice(BaseModel):
    address: str
    response: str
    fingerprint: Optional[DeviceFingerprint] = None


# ---------------------------------------------------------------------------
# Aggregate response
# ---------------------------------------------------------------------------

class DiscoverResponse(BaseModel):
    upnp: List[UPnPDevice] = Field(default_factory=list)
    mdns: List[MDNSService] = Field(default_factory=list)
    wsd: List[WSDDevice] = Field(default_factory=list)
