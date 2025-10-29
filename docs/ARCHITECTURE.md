# FireFly Architecture

## Overview
FireFly is a modular IoT device discovery tool composed of:
- A FastAPI backend that performs multi-protocol network discovery (UPnP/SSDP, mDNS/Zeroconf, WS-Discovery) and exposes REST endpoints.
- A React (Create React App + Material UI) frontend that drives discovery and presents results.
- Dockerized services orchestrated via Docker Compose for local development and demos.

## Components

### Backend (FastAPI)
- Entrypoint: `main.py`
- Framework: FastAPI + Uvicorn
- API Endpoints:
  - `GET /api/health` → Liveness check
  - `GET /api/discover` → Triggers discovery across selected protocols with query parameters:
    - `protocol`: `all|upnp|mdns|wsd`
    - `timeout`: 1–300 seconds (default from settings)
    - `mdns_service`: service type or `all`
    - `upnp_st`, `upnp_mx`, `upnp_ttl`
    - `interface_ip`: optional bind interface (non-loopback)
- Configuration: `config.py` with `AppSettings` (Pydantic v2) sourced from environment variables:
  - `LOG_LEVEL`, `DEFAULT_TIMEOUT`, `MAX_TIMEOUT`, `ALLOWED_ORIGINS`, `UPNP_DEFAULT_*`
- Schemas: `schemas.py` defines request validation and response models for each protocol’s output.
- CORS: Configured from `allowed_origins`, defaulting to localhost dev origins.
- Logging: Configured via `LOG_LEVEL` (default INFO) on startup.

#### Protocol Modules (`protocols/`)
1. `upnp.py`
   - Sends SSDP M-SEARCH to `239.255.255.250:1900` with configurable `ST`, `MX`, `TTL`.
   - Parses responses, annotates source `address`.
   - Optional enrichment: fetches `LOCATION` device description XML (defensive SSRF controls: http/https only, private/link-local/loopback only, no redirects, hostname resolved and validated).
   - Extracts `<friendlyName>` and `<deviceType>` into device dict.

2. `mdns.py`
   - Uses Zeroconf `ServiceBrowser` to discover services.
   - Supports browsing meta-service `_services._dns-sd._udp.local.` to enumerate available service types.
   - Collects `addresses`, `port`, and `properties` when available.
   - Optional `interface_ip` binding via Zeroconf initialization.

3. `ws_discovery.py`
   - Sends WS-Discovery SOAP `Probe` to `239.255.255.250:3702` with configurable `TTL`.
   - Returns responder `address` and raw XML `response` payloads.
   - Optional `interface_ip` for socket bind and multicast interface selection.

### Frontend (React + MUI)
- Location: `firefly/`
- Stack: CRA + React 18, Material UI v5, Axios.
- Configuration:
  - `REACT_APP_API_URL` env var (from Compose) or fallback to `window.location` host:port `:8000`.
- UI Features:
  - Protocol selector, mDNS service type, UPnP ST/MX/TTL, global timeout, optional interface IP.
  - Scan action calls `/api/discover` with params; results persisted to `localStorage`.
  - Results grid grouped by protocol with cards showing device attributes; export JSON/CSV; optional raw JSON toggle; error toasts.

### Containerization (Docker & Compose)
- Compose file: `docker-compose.yml`
  - `backend`: builds from repo root (`Dockerfile`), exposes `8000:8000`, env defaults for logging and timeouts.
  - `frontend`: builds from `firefly/Dockerfile`, exposes `3000:3000`, sets `REACT_APP_API_URL=http://localhost:8000`.
  - Shared user-defined network `firefly` for service-to-service traffic.
- Backend Dockerfile:
  - Base: `python:3.11-slim`
  - Installs `requirements.txt`, copies source, starts `uvicorn main:app` on `0.0.0.0:8000`.
- Frontend Dockerfile:
  - Base: `node:18-alpine`
  - `npm ci`, dev server on `0.0.0.0:3000` using CRA.

## Data Flow
1. Frontend issues `GET /api/discover` with selected options.
2. Backend validates parameters (`schemas.py`), normalizes effective timeout (`config.py`).
3. Backend executes selected discovery modules, aggregates results into `DiscoverResponse`.
4. Frontend presents grouped results, offering export options.

## Security Considerations
- SSRF mitigations when fetching UPnP `LOCATION`:
  - Only http/https; validate destination IP (private/link-local/loopback); do not follow redirects; ignore proxies.
- CORS restricted to development origins by default; configurable via `ALLOWED_ORIGINS`.
- Loopback binding explicitly rejected for `interface_ip` on `/api/discover`.

## Operational Notes
- Multicast discovery inside containers may require host networking or additional Docker config in some environments. Current Compose uses bridge networking which is fine for many setups, but for broader network segment discovery you may consider `network_mode: host` (Linux) or run backend on the host.
- Timeouts are bounded by `MAX_TIMEOUT` to protect server responsiveness.

## Local Development
- Backend: `python main.py` or `uvicorn main:app --reload`.
- Frontend: `cd firefly && npm start`.
- Docker: `docker compose up --build -d` then visit `http://localhost:3000`.

## Known Limitations
- Discovery fidelity may vary in containerized environments due to multicast forwarding.
- Frontend is JavaScript (no TypeScript types) and uses CRA dev server in container.

---

# Proposed Improvements

## Backend (Senior Backend, SecOps)
- Structured JSON logging with request IDs; include protocol timings and counts.
- Add `/metrics` (Prometheus) and basic request rate limiting.
- Harden SSRF controls further: restrict ports, disallow redirects explicitly (already off), clamp content length, set UA, and limit XML entity expansion (using `defusedxml` already good).
- Expose `settings` via Pydantic Settings with `env_prefix="FIREFLY_"` and typed `.env` support.
- Add graceful shutdown and cancellation for in-flight discovery.
- Provide `network_mode` guidance for multicast (docs + optional Compose profile).
- Testing: pytest coverage for parsers, SSRF guards, and schemas.
- Tooling: `ruff` + `black` + `isort` + `mypy` + `bandit` + pre-commit hooks.

## Frontend (Senior Frontend, UI/UX)
- Convert to TypeScript, add API types (mirror `schemas.py`).
- Introduce query state management (React Query) with caching and retries.
- Improve list UX: filters, search, grouping, expanders for details, copy-to-clipboard.
- Loading skeletons and empty-state guidance; preserve settings more granularly.
- Upgrade to Vite or keep CRA but add production build in container.
- Fix vulnerabilities (run `npm audit fix`), pin deps via lockfile updates.

## DevOps/SecOps
- Compose:
  - Add `healthcheck` for both services.
  - Resource limits (CPU/memory) and restart policy.
  - Run backend as non-root, read-only FS, drop Linux capabilities.
  - Profiles: `dev` (current) and `prod` (frontend served as static build behind backend or minimal Nginx).
- Supply `.env.example` and document required vars.
- CI: GitHub Actions for lint, test, Docker build, SAST (Bandit), dependency updates (Dependabot/Renovate).

## Process (Team Lead)
- Branching: trunk-based with short-lived feature branches; conventional commits.
- PR templates, CODEOWNERS for backend/frontend ownership, review checklists.
- Definition of Done: tests, lint, docs updated, security checklist passed.

---

## Suggested Next Steps
1. Add healthchecks and non-root Docker users; create `prod` profile.
2. Introduce pre-commit with ruff/black/isort/mypy/bandit.
3. Add pytest and initial unit tests for protocol parsers and SSRF safeguards.
4. Convert frontend to TypeScript incrementally or add typing via JSDoc; add React Query.
5. Set up CI with lint/test/build and dependency monitoring.


