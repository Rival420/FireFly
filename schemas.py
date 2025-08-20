from typing import Dict, List, Optional

from pydantic import BaseModel, Field, constr, conint


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


class UPnPDevice(BaseModel):
    address: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    LOCATION: Optional[str] = None
    USN: Optional[str] = None
    SERVER: Optional[str] = None
    ST: Optional[str] = None


class MDNSService(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    addresses: Optional[List[str]] = None
    port: Optional[int] = None
    properties: Optional[Dict[str, str]] = None


class WSDDevice(BaseModel):
    address: str
    response: str


class DiscoverResponse(BaseModel):
    upnp: List[UPnPDevice] = Field(default_factory=list)
    mdns: List[MDNSService] = Field(default_factory=list)
    wsd: List[WSDDevice] = Field(default_factory=list)

