# FireFly — Modular IoT Discovery (UPnP, mDNS, WS-Discovery)

FireFly is a modular, multi-protocol IoT discovery toolkit:
- FastAPI backend exposing a safe `/api/discover` endpoint
- React 18 + Material UI 5 frontend for a clean, accessible UI
- Protocol modules for UPnP/SSDP, mDNS/Zeroconf, and WS-Discovery

---

## What’s inside
- Multi-protocol discovery with strict validation and SSRF guardrails
- Typed schemas (Pydantic v2) and clear API docs (Swagger)
- Dockerfiles and Docker Compose for a one-command dev/demo setup

---

## Quickstart

### Run locally (host)
Backend (FastAPI):
```bash
uvicorn main:app --reload
```

Frontend (React):
```bash
cd firefly
npm install
npm start
```

### Run with Docker Compose

#### Default (full stack, bridge network)
```bash
docker compose up --build -d
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

#### Linux — host networking (best multicast reach)
Uses `network_mode: host` so the backend can send/receive multicast directly on the LAN.

```bash
docker compose --profile hostnet up --build -d backend_hostnet frontend

# Stop
docker compose --profile hostnet down
```

#### Raspberry Pi
A Pi on your LAN is the ideal setup for always-on IoT discovery. It runs Linux, so
host networking works natively and the ARM images build out of the box (`python:3.11-slim`
and `node:18-alpine` both support `arm64`/`armv7`).

```bash
# Clone and start with host networking (recommended for Pi)
git clone https://github.com/Rival420/FireFly.git && cd FireFly
docker compose --profile hostnet up --build -d backend_hostnet frontend

# Frontend: http://<pi-ip>:3000
# Backend:  http://<pi-ip>:8000
# Swagger:  http://<pi-ip>:8000/docs
```

> **Tip:** Bookmark `http://<pi-ip>:3000` on any device on your network to scan
> from your phone/laptop while the Pi does the actual multicast probing.

#### macOS / Windows — backend on host
Docker Desktop runs containers in a Linux VM, so multicast never reaches the physical
LAN. Run the backend on your host and only the frontend in Docker:

```bash
# 1. Backend on host (real network access for multicast)
pip install -r requirements.txt          # first time only
uvicorn main:app --host 0.0.0.0 --port 8000

# 2. Frontend in Docker
docker compose up --build -d frontend
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

### Run as Docker images (separate containers)
Backend image:
```bash
docker build -t firefly-backend:local .
docker run --rm -p 8000:8000 \
  -e LOG_LEVEL=INFO -e DEFAULT_TIMEOUT=5 -e MAX_TIMEOUT=30 \
  firefly-backend:local
# Swagger: http://localhost:8000/docs
```

Frontend image:
```bash
docker build -t firefly-frontend:local -f firefly/Dockerfile firefly
docker run --rm -p 3000:3000 \
  -e REACT_APP_API_URL=http://host.docker.internal:8000 \
  firefly-frontend:local
# App: http://localhost:3000
```

Note (multicast in containers): UDP multicast for discovery may be limited depending on your Docker/network setup. If you need broader L2 visibility on Linux, you can run the backend with host networking (security trade-offs):
```bash
docker run --rm --network host firefly-backend:local
```

---

## API

### Endpoint
`GET /api/discover`

Query parameters:
- `protocol`: `all|upnp|mdns|wsd` (default: `all`)
- `timeout`: integer seconds, 1–300 (default from server settings)
- `mdns_service`: service type or `all` (default: `_services._dns-sd._udp.local.`)
- `upnp_st`: UPnP Search Target (default: `ssdp:all`)
- `upnp_mx`: UPnP MX 1–5 (default: 3)
- `upnp_ttl`: Multicast TTL 1–16 (default: 2)
- `interface_ip`: optional source IP to bind (non-loopback)

Security and limits:
- Optional API key: set `API_KEY` on the backend and send header `X-API-Key`
- Basic rate limit: 10 requests/60s per client

Example:
```bash
curl "http://localhost:8000/api/discover?protocol=upnp&timeout=5&mdns_service=_services._dns-sd._udp.local."
```

### Health and metrics
- Liveness: `GET /api/healthz` → 200 when process is up
- Readiness: `GET /api/readyz` → 200 when ready; 503 during shutdown
- Metrics (stub): `GET /api/metrics/health` returns simple counters

### API Docs
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Configuration
Environment variables (see `config.py`):
- `LOG_LEVEL` (default `INFO`)
- `DEFAULT_TIMEOUT`, `MAX_TIMEOUT` (defaults 5/30)
- `ALLOWED_ORIGINS` (CSV; defaults to local dev origins)
- `UPNP_DEFAULT_ST`, `UPNP_DEFAULT_MX`, `UPNP_DEFAULT_TTL`
- `API_KEY` (optional; enables `X-API-Key` auth on `/api/discover`)

---

## Architecture (ASCII overview)
```
                          +--------------------------+
                          |  React Frontend (MUI)   |
                          |  firefly/:3000          |
                          +-----------+--------------+
                                      |  GET /api/discover
                                      v
+-----------------------+   validates/limits   +-----------------------------+
|     Schemas/Config    | <------------------> |   FastAPI Backend (:8000)   |
|  (pydantic, settings) |                      |   routes under /api/*       |
+-----------------------+                      +---------------+-------------+
                                                                |
                                                                | calls
                                                                v
                                                  +-------------+-------------+
                                                  |          Protocols        |
                                                  |  UPnP   mDNS   WS-Disc.   |
                                                  +------+------+------+------+
                                                         |      |      |
                                                UDP multicast   |      |
                                                         |      |      |
                                                         v      v      v
                                                   Network devices/services

Notes:
- UPnP enrichment fetch obeys SSRF guardrails (http/https only, private/link-local/loopback IPs, no redirects, size/content-type limits, ignores proxies).
- `interface_ip` cannot be loopback; discovery sockets bind to it when provided.
```

---

## Mermaid — data/code flow
```mermaid
flowchart LR
  UI[React UI] -->|GET /api/discover| API[FastAPI validate/normalize]
  API -->|protocol==upnp| U[UPnPDiscovery]
  API -->|protocol==mdns| M[mDNSDiscovery]
  API -->|protocol==wsd|  W[WS-Discovery]
  API -->|protocol==all|  U & M & W
  U --> AGG[Aggregate]
  M --> AGG
  W --> AGG
  AGG --> RESP[DiscoverResponse JSON]
  UI <-- RESP

  subgraph Guards
    API --- X1[Rate limit 10/min]
    API --- X2[Optional X-API-Key]
    U --- X3[SSRF-safe enrichment]
    API --- X4[interface_ip validation]
  end
```

---

## Frontend (TypeScript + React Query)
- React 18 + MUI v5 UI with protocol selector, timeout, mDNS service, and optional interface IP
- Determinate progress, cancel, search, pagination
- Export JSON/CSV, link to Swagger

## Known limitations
- Multicast discovery can be constrained inside containers/VMs; host networking may be needed in some setups

## Contributing
PRs welcome. Please use conventional commits and keep changes small and focused. Include tests where appropriate.

License: MIT