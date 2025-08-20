from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from protocols import upnp, mdns, ws_discovery
from schemas import DiscoverQuery, DiscoverResponse
from config import get_settings
import logging
import ipaddress

app = FastAPI(
    title="IoT Device Discovery API",
    version="1.0",
    description="A REST API to discover IoT devices using UPnP, mDNS, and WS-Discovery."
)

settings = get_settings()

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("firefly")

# Enable CORS for configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/api/health", response_model=dict)
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/discover", response_model=DiscoverResponse)
def discover(
    protocol: str = Query("all", description="upnp|mdns|wsd|all"),
    timeout: int = Query(None, description="Timeout seconds (1-300)"),
    mdns_service: str = Query("_services._dns-sd._udp.local.", description="mDNS service or 'all'"),
    upnp_st: str = Query("ssdp:all", description="UPnP search target"),
    upnp_mx: int = Query(3, description="UPnP MX (1-5)"),
    upnp_ttl: int = Query(2, description="Multicast TTL (1-16)"),
    interface_ip: str = Query(None, description="Optional interface IP to bind to"),
):
    # Validate and normalize inputs using Pydantic schema
    try:
        effective_timeout = timeout or settings.default_timeout_seconds
        query = DiscoverQuery(
            protocol=protocol,
            timeout=min(max(effective_timeout, 1), settings.max_timeout_seconds),
            mdns_service=mdns_service,
            upnp_st=upnp_st,
            upnp_mx=upnp_mx,
            upnp_ttl=upnp_ttl,
            interface_ip=interface_ip,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Basic SSRF defense for LOCATION fetches relies on downstream logic; we also restrict interface_ip if provided
    if query.interface_ip:
        try:
            ip = ipaddress.ip_address(query.interface_ip)
            if ip.is_loopback:
                raise HTTPException(status_code=400, detail="Refusing to bind to loopback interface for discovery")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid interface_ip")

    results: dict = {"upnp": [], "mdns": [], "wsd": []}

    # UPnP Discovery
    if query.protocol in ("all", "upnp"):
        upnp_results = upnp.UPnPDiscovery(
            timeout=query.timeout,
            st=query.upnp_st,
            mx=query.upnp_mx,
            multicast_ttl=query.upnp_ttl,
            verbose=False,
            interface_ip=query.interface_ip,
        ).discover()
        results["upnp"] = upnp_results

    # mDNS Discovery
    if query.protocol in ("all", "mdns"):
        mdns_results = []
        if query.mdns_service.lower() == "all":
            well_known_services = [
                "_services._dns-sd._udp.local.",
                "_http._tcp.local.",
                "_workstation._tcp.local.",
                "_ipp._tcp.local.",
                "_printer._tcp.local.",
            ]
            for service in well_known_services:
                mdns_results.extend(
                    mdns.MDNSDiscovery(timeout=query.timeout, service_type=service, interface_ip=query.interface_ip).discover()
                )
        else:
            mdns_results = mdns.MDNSDiscovery(
                timeout=query.timeout, service_type=query.mdns_service, interface_ip=query.interface_ip
            ).discover()
        results["mdns"] = mdns_results

    # WS-Discovery
    if query.protocol in ("all", "wsd"):
        wsd_results = ws_discovery.WSDiscovery(timeout=query.timeout, multicast_ttl=query.upnp_ttl, interface_ip=query.interface_ip).discover()
        results["wsd"] = wsd_results

    return JSONResponse(content=DiscoverResponse(**results).model_dump())

if __name__ == "__main__":
    # Run the API with: uvicorn main:app --reload
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)