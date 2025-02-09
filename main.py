from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from protocols import upnp, mdns, ws_discovery

app = FastAPI(
    title="IoT Device Discovery API",
    version="1.0",
    description="A REST API to discover IoT devices using UPnP, mDNS, and WS-Discovery."
)

# Enable CORS so that our React front end can call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/discover")
def discover(
    protocol: str = Query("all", description="Discovery protocol: upnp, mdns, wsd, or all"),
    timeout: int = Query(5, description="Timeout for discovery (in seconds)"),
    mdns_service: str = Query("_services._dns-sd._udp.local.", description="Service type for mDNS (if protocol is mdns)")
):
    results = {}

    # UPnP Discovery
    if protocol in ("all", "upnp"):
        upnp_results = upnp.UPnPDiscovery(timeout=timeout).discover()
        results["upnp"] = upnp_results

    # mDNS Discovery
    if protocol in ("all", "mdns"):
        mdns_results = []
        if mdns_service.lower() == "all":
            # Cycle through a list of common mDNS service types.
            well_known_services = [
                "_services._dns-sd._udp.local.",
                "_http._tcp.local.",
                "_workstation._tcp.local.",
                "_ipp._tcp.local.",
                "_printer._tcp.local."
            ]
            for service in well_known_services:
                mdns_results.extend(mdns.MDNSDiscovery(timeout=timeout, service_type=service).discover())
        else:
            mdns_results = mdns.MDNSDiscovery(timeout=timeout, service_type=mdns_service).discover()
        results["mdns"] = mdns_results

    # WS-Discovery
    if protocol in ("all", "wsd"):
        wsd_results = ws_discovery.WSDiscovery(timeout=timeout).discover()
        results["wsd"] = wsd_results

    return results

if __name__ == "__main__":
    # Run the API with: uvicorn main:app --reload
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
