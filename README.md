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
   Frontend Setup
   ```
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
Contributions are welcome! Please feel free to open issues or submit pull requests. When contributing, try to follow the modular design 
