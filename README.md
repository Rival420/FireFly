# FireFly - IoT Discovery Tool
FireFly is a modular, multi-protocol IoT device discovery framework that allows you to scan your network for devices using several auto-discovery protocols:
- **UPnP (SSDP)**
- **mDNS (via Zeroconf)**
- **WS-Discovery**

It comes with a **FastAPI** backend that exposes a REST API for device discovery and a modern **React** front end built with Material-UI for a sleek and responsive user interface.

## Features

- **Multi-Protocol Discovery:**  
  Discover IoT devices using UPnP, mDNS, and WS-Discovery.

- **Modular Design:**  
  Each protocol is implemented in its own module for easy maintenance and future extension.

- **FastAPI Backend:**  
  Provides a REST API endpoint (`/api/discover`) to trigger scans and return discovery results in JSON format.

- **Modern React Frontend:**  
  A responsive UI built with React and Material-UI that lets you select protocols, adjust settings (e.g., timeout, mDNS service), and view discovered devices.

- **Concurrently Run Backend and Frontend:**  
  Option to run both services concurrently using tools like `concurrently` for streamlined development.

## Project Structure

## Prerequisites

- **Python 3.7+**  
- **Node.js & npm**  
- (Optional) **Virtual Environment** for Python dependencies

## Installation

### Backend Setup

1. **Create and Activate a Virtual Environment (Recommended):**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Python Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

### Frontend Setup

3. **Navigate to the Frontend Directory:**

   ```bash
   cd firefly
   ```

4. **Install Node.js Dependencies:**

   ```bash
   npm install
   ```

5. **Running the Application**
Option 1: Run Services Separately
* Start the Backend (from the project root):
   ```bash
   python main.py
   ```
* Start the Frontend (from the firefly directory):
   ```bash
   npm start
   ```

6. API Usage
The FastAPI backend exposes an endpoint at:

   ```arduino
   http://<backend_ip>:8000/api/discover
   ```
Query parameters include:

protocol: Select a protocol (upnp, mdns, wsd, or all).
timeout: Set the timeout in seconds.
mdns_service: Specify the mDNS service type (or "All" to cycle through common services).
For example:

`http://<backend_ip>:8000/api/discover?protocol=upnp&timeout=5&mdns_service=_services._dns-sd._udp.local.`

Contributing
Contributions are welcome! Please feel free to open issues or submit pull requests. When contributing, try to follow the modular design  of the project so that new discovery protocols or front-end enhancements integrate smoothly.

---

Security notes:
- Only use this tool on networks you own or have explicit permission to test.
- Backend applies SSRF safeguards for UPnP `LOCATION` fetches, configurable CORS, and strict input validation.
- Prefer running in an isolated lab when experimenting with offensive techniques.
 - Optional API key: set `API_KEY` to require header `X-API-Key` on `/api/discover`.
 - Basic rate limit: 10 requests/min per client for `/api/discover`.

Additional API parameters:
- `upnp_st`, `upnp_mx`, `upnp_ttl`: UPnP tuning parameters
- `interface_ip`: Optional local IP to bind discovery sockets (non-loopback)

## Healthchecks
- Liveness: `GET /api/healthz` → 200 when process is up
- Readiness: `GET /api/readyz` → 200 when app is ready (503 during shutdown)
- Dockerfile and Compose include healthchecks for backend and frontend containers.

### Metrics (stub)
- `GET /api/metrics/health` returns JSON counters for `healthz` and `readyz`.

## API Docs
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Frontend (TypeScript + React Query)
- The frontend is fully converted to TypeScript and uses React Query for discovery.
- Key UX features:
  - Determinate scan progress with cancel
  - Protocol tabs with counts, search, and pagination
  - Export JSON/CSV, API Docs button linking to Swagger UI
- Running in Docker performs all installs inside the container; no host installs are required.

## CRA Deprecation Notes
- Create React App shows deprecation warnings. A follow-up migration path is documented in `docs/FRONTEND_MIGRATION.md` (e.g., migrate to Vite) but not required to run the app.