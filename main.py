from fastapi import FastAPI, HTTPException, Query, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from protocols import upnp, mdns, ws_discovery
from schemas import DiscoverQuery, DiscoverResponse, ErrorResponse
from config import get_settings
import logging
import ipaddress
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="FireFly IoT Discovery API",
    version="1.0",
    summary="Modular multi-protocol IoT discovery (UPnP, mDNS, WS-Discovery)",
    description=(
        "FireFly exposes a safe, modular API to discover devices on local networks "
        "using UPnP/SSDP, mDNS/Zeroconf, and WS-Discovery with strong input validation "
        "and SSRF guardrails for enrichment."
    ),
    terms_of_service="https://example.com/terms",
    contact={
        "name": "FireFly Team",
        "url": "https://example.com/firefly",
        "email": "support@example.com",
    },
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

settings = get_settings()

# Readiness flag
app.state.ready = False
app.state.health_metrics = {"healthz": 0, "readyz_ok": 0, "readyz_fail": 0}
app.state.rate_limits = {}

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("firefly")

# Enable CORS for configured origins.
# Also allow X-API-Key header so the optional auth works cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

openapi_tags = [
    {"name": "health", "description": "Service liveness and readiness"},
    {"name": "discovery", "description": "IoT device discovery endpoints"},
    {"name": "metrics", "description": "Operational metrics"},
]


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["tags"] = openapi_tags
    openapi_schema["servers"] = [
        {"url": "http://localhost:8000", "description": "Local development"},
        {"url": "http://firefly-backend:8000", "description": "Docker Compose"},
    ]
    openapi_schema["externalDocs"] = {
        "description": "Project README",
        "url": "https://github.com/Rival420/FireFly",
    }
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
        {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Optional API key header when enabled by deployment",
            }
        }
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[assignment]


@app.on_event("startup")
def on_startup() -> None:
    app.state.ready = True


@app.on_event("shutdown")
def on_shutdown() -> None:
    app.state.ready = False


@app.get("/api/health", response_model=dict, tags=["health"], summary="Basic health check")
def health() -> dict:
    app.state.health_metrics["healthz"] += 1
    return {"status": "ok"}


@app.get("/api/healthz", response_model=dict, tags=["health"], summary="Liveness probe")
def healthz() -> dict:
    app.state.health_metrics["healthz"] += 1
    return {"status": "ok"}


@app.get(
    "/api/readyz",
    response_model=dict,
    tags=["health"],
    summary="Readiness probe",
    responses={
        200: {"description": "Service is ready"},
        503: {"model": ErrorResponse, "description": "Service not ready"},
    },
)
def readyz() -> JSONResponse:
    if getattr(app.state, "ready", False):
        app.state.health_metrics["readyz_ok"] += 1
        return JSONResponse(status_code=200, content={"ready": True})
    app.state.health_metrics["readyz_fail"] += 1
    return JSONResponse(status_code=503, content={"ready": False, "detail": "initializing"})


@app.get("/api/metrics/health", response_model=dict, tags=["metrics"], summary="Health endpoint counters")
def health_metrics() -> dict:
    # Simple JSON metrics stub; intended for future Prometheus export
    return app.state.health_metrics


@app.get("/api/diagnostics", tags=["health"], summary="Network diagnostics for multicast discovery")
def diagnostics() -> dict:
    """Check network interfaces, multicast capability, and run a quick SSDP probe."""
    import socket
    import struct
    import platform
    import time
    import netifaces  # noqa: might not be installed — handled below

    result: dict = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "interfaces": {},
        "multicast_socket": {"ok": False, "error": None},
        "ssdp_probe": {"sent": False, "responses": 0, "devices": [], "error": None},
        "mdns_socket": {"ok": False, "error": None},
    }

    # ---- 1. Network interfaces ----
    try:
        import ifaddr
        for adapter in ifaddr.get_adapters():
            ips = [ip.ip for ip in adapter.ips if isinstance(ip.ip, str) and not ip.ip.startswith("127.")]
            if ips:
                result["interfaces"][adapter.nice_name] = ips
    except Exception as exc:
        result["interfaces"]["error"] = str(exc)

    # ---- 2. Can we create a multicast UDP socket? ----
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.close()
        result["multicast_socket"] = {"ok": True, "error": None}
    except Exception as exc:
        result["multicast_socket"] = {"ok": False, "error": str(exc)}

    # ---- 3. Quick SSDP probe (2 second timeout) ----
    try:
        probe_timeout = 2
        msg = "\r\n".join([
            "M-SEARCH * HTTP/1.1",
            "HOST:239.255.255.250:1900",
            'MAN:"ssdp:discover"',
            "MX:1",
            "ST:ssdp:all",
            "", ""
        ])
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(probe_timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(msg.encode(), ("239.255.255.250", 1900))
        result["ssdp_probe"]["sent"] = True

        start = time.time()
        devices = []
        while time.time() - start < probe_timeout:
            try:
                data, addr = sock.recvfrom(4096)
                devices.append(addr[0])
            except socket.timeout:
                break
        sock.close()
        result["ssdp_probe"]["responses"] = len(devices)
        result["ssdp_probe"]["devices"] = list(set(devices))
    except Exception as exc:
        result["ssdp_probe"]["error"] = str(exc)

    # ---- 4. Can Zeroconf initialize? ----
    try:
        from zeroconf import Zeroconf
        zc = Zeroconf()
        zc.close()
        result["mdns_socket"] = {"ok": True, "error": None}
    except Exception as exc:
        result["mdns_socket"] = {"ok": False, "error": str(exc)}

    return result


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


def rate_limit(request: Request) -> None:
    # Very simple in-memory rate limiter (per-client): max 10 req per 60s
    import time

    window_seconds = 60
    max_requests = 10
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = app.state.rate_limits.setdefault(client_ip, [])
    # drop timestamps older than window
    app.state.rate_limits[client_ip] = [t for t in bucket if now - t < window_seconds]
    if len(app.state.rate_limits[client_ip]) >= max_requests:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    app.state.rate_limits[client_ip].append(now)


@app.get(
    "/api/discover",
    response_model=DiscoverResponse,
    tags=["discovery"],
    summary="Discover devices across selected protocols",
    responses={
        200: {"description": "Discovery results grouped by protocol"},
        400: {"model": ErrorResponse, "description": "Invalid input parameters"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Too Many Requests"},
    },
)
def discover(
    protocol: str = Query("all", description="upnp|mdns|wsd|all"),
    timeout: int = Query(None, description="Timeout seconds (1-300)"),
    mdns_service: str = Query("_services._dns-sd._udp.local.", description="mDNS service or 'all'"),
    upnp_st: str = Query("ssdp:all", description="UPnP search target"),
    upnp_mx: int = Query(3, description="UPnP MX (1-5)"),
    upnp_ttl: int = Query(2, description="Multicast TTL (1-16)"),
    interface_ip: str = Query(None, description="Optional interface IP to bind to"),
    enrich: bool = Query(False, description="Enable deep enumeration and fingerprinting"),
    _=Depends(verify_api_key),
    __=Depends(rate_limit),
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
            enrich=enrich,
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
        if query.mdns_service.lower() == "all":
            well_known_services = [
                "_services._dns-sd._udp.local.",
                "_http._tcp.local.",
                "_workstation._tcp.local.",
                "_ipp._tcp.local.",
                "_printer._tcp.local.",
            ]
            # Browse all service types simultaneously with a single Zeroconf
            # instance — avoids the old sequential loop that created/destroyed
            # five separate instances and left sockets in TIME_WAIT.
            mdns_results = mdns.MDNSDiscovery(
                timeout=query.timeout,
                interface_ip=query.interface_ip,
            ).discover(service_types=well_known_services)
        else:
            mdns_results = mdns.MDNSDiscovery(
                timeout=query.timeout,
                service_type=query.mdns_service,
                interface_ip=query.interface_ip,
            ).discover()
        results["mdns"] = mdns_results

    # WS-Discovery
    if query.protocol in ("all", "wsd"):
        wsd_results = ws_discovery.WSDiscovery(timeout=query.timeout, multicast_ttl=query.upnp_ttl, interface_ip=query.interface_ip).discover()
        results["wsd"] = wsd_results

    # Deep enumeration & fingerprinting (when requested)
    if query.enrich:
        from protocols.enrichment import (
            build_default_pipeline,
            devices_from_results,
            apply_enrichment,
        )
        pipeline = build_default_pipeline()
        device_infos = devices_from_results(results)
        enriched = pipeline.enrich_all(device_infos, timeout=query.timeout)
        results = apply_enrichment(results, enriched)
        logger.info("Enrichment complete — %d devices fingerprinted", len(enriched))

    return JSONResponse(content=DiscoverResponse(**results).model_dump())

if __name__ == "__main__":
    # Run the API with: uvicorn main:app --reload
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)