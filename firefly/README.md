# FireFly Frontend (React 18 + MUI 5)

This is the React application for FireFly. It talks to the backend at `REACT_APP_API_URL` (defaults to the current host on port `8000`).

## Run (host)
```bash
npm install
npm start
# http://localhost:3000
```

Optionally set the backend URL:
```bash
REACT_APP_API_URL=http://localhost:8000 npm start
```

## Run (Docker)
```bash
docker build -t firefly-frontend:local -f Dockerfile .
docker run --rm -p 3000:3000 \
  -e REACT_APP_API_URL=http://host.docker.internal:8000 \
  firefly-frontend:local
```

For full-stack usage and more details, see the root README.
