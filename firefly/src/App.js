import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Container,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Snackbar,
  Alert,
  Switch,
  FormControlLabel,
} from "@mui/material";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import "./App.css";

// Create a dark theme using Material UI.
const darkTheme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: "#121212",
      paper: "#1d1d1d",
    },
    primary: {
      main: "#90caf9",
    },
    text: {
      primary: "#ffffff",
    },
  },
});

// Use an environment variable for the API URL or default to localhost.
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

function App() {
  // State for discovery results and loading indicator.
  const [devices, setDevices] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showRaw, setShowRaw] = useState(false);

  // General discovery settings.
  const [protocol, setProtocol] = useState("all");
  const [timeoutVal, setTimeoutVal] = useState(5);
  const [mdnsService, setMdnsService] = useState("_services._dns-sd._udp.local.");
  const [interfaceIp, setInterfaceIp] = useState("");

  // UPnP-specific options.
  const [upnpST, setUpnpST] = useState("ssdp:all");
  const [upnpMX, setUpnpMX] = useState(3);
  const [upnpTTL, setUpnpTTL] = useState(2);

  // Fetch devices from the API.
  const fetchDevices = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/discover`, {
        params: {
          protocol: protocol,
          timeout: timeoutVal,
          mdns_service: mdnsService,
          upnp_st: upnpST,
          upnp_mx: upnpMX,
          upnp_ttl: upnpTTL,
          interface_ip: interfaceIp || undefined,
        },
      });
      setDevices(response.data);
      localStorage.setItem(
        "firefly_settings",
        JSON.stringify({ protocol, timeoutVal, mdnsService, upnpST, upnpMX, upnpTTL, interfaceIp })
      );
    } catch (error) {
      console.error("Error fetching devices:", error);
      setError(error?.response?.data?.detail || error.message || "Request failed");
    } finally {
      setLoading(false);
    }
  };

  // Optionally auto-fetch on mount.
  useEffect(() => {
    try {
      const saved = localStorage.getItem("firefly_settings");
      if (saved) {
        const s = JSON.parse(saved);
        if (s.protocol) setProtocol(s.protocol);
        if (s.timeoutVal) setTimeoutVal(s.timeoutVal);
        if (s.mdnsService) setMdnsService(s.mdnsService);
        if (s.upnpST) setUpnpST(s.upnpST);
        if (s.upnpMX) setUpnpMX(s.upnpMX);
        if (s.upnpTTL) setUpnpTTL(s.upnpTTL);
        if (s.interfaceIp) setInterfaceIp(s.interfaceIp);
      }
    } catch (_) {}
    // fetchDevices();
  }, []);

  const download = (filename, text) => {
    const element = document.createElement("a");
    element.setAttribute(
      "href",
      "data:text/plain;charset=utf-8," + encodeURIComponent(text)
    );
    element.setAttribute("download", filename);
    element.style.display = "none";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const exportJson = () => download("firefly_results.json", JSON.stringify(devices, null, 2));
  const exportCsv = () => {
    try {
      const rows = [];
      Object.entries(devices).forEach(([proto, list]) => {
        list.forEach((d) => {
          rows.push({ proto, ...d });
        });
      });
      if (!rows.length) return;
      const headers = Array.from(
        rows.reduce((set, row) => {
          Object.keys(row).forEach((k) => set.add(k));
          return set;
        }, new Set())
      );
      const csv = [headers.join(",")]
        .concat(
          rows.map((r) => headers.map((h) => JSON.stringify(r[h] ?? "")).join(","))
        )
        .join("\n");
      download("firefly_results.csv", csv);
    } catch (e) {
      setError("Export failed");
    }
  };

  return (
    <ThemeProvider theme={darkTheme}>
      <Container className="app-container">
        <Typography variant="h3" align="center" gutterBottom>
          Firefly - IoT Device Discovery
        </Typography>

        <Grid container spacing={2} justifyContent="center" alignItems="center">
          {/* Protocol Selection */}
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth>
              <InputLabel id="protocol-label">Protocol</InputLabel>
              <Select
                labelId="protocol-label"
                value={protocol}
                label="Protocol"
                onChange={(e) => setProtocol(e.target.value)}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="upnp">UPnP</MenuItem>
                <MenuItem value="mdns">mDNS</MenuItem>
                <MenuItem value="wsd">WS-Discovery</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          {/* mDNS Service Field */}
          {(protocol === "all" || protocol === "mdns") && (
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="mDNS Service"
                value={mdnsService}
                onChange={(e) => setMdnsService(e.target.value)}
                helperText='e.g. "_services._dns-sd._udp.local." or "All"'
              />
            </Grid>
          )}

          {/* UPnP Fields: Shown when protocol is "all" or "upnp" */}
          {(protocol === "all" || protocol === "upnp") && (
            <>
              <Grid item xs={12} sm={3}>
                <TextField
                  fullWidth
                  label="UPnP ST"
                  value={upnpST}
                  onChange={(e) => setUpnpST(e.target.value)}
                  helperText='Search Target (e.g., "ssdp:all" or "upnp:rootdevice")'
                />
              </Grid>
              <Grid item xs={12} sm={2}>
                <TextField
                  fullWidth
                  type="number"
                  label="UPnP MX"
                  value={upnpMX}
                  onChange={(e) => setUpnpMX(Number(e.target.value))}
                  helperText="MX (max wait time)"
                />
              </Grid>
              <Grid item xs={12} sm={2}>
                <TextField
                  fullWidth
                  type="number"
                  label="UPnP TTL"
                  value={upnpTTL}
                  onChange={(e) => setUpnpTTL(Number(e.target.value))}
                  helperText="Multicast TTL"
                />
              </Grid>
            </>
          )}

          {/* Timeout Field */}
          <Grid item xs={12} sm={2}>
            <TextField
              fullWidth
              type="number"
              label="Timeout (s)"
              value={timeoutVal}
              onChange={(e) => setTimeoutVal(Number(e.target.value))}
            />
          </Grid>

          {/* Interface IP */}
          <Grid item xs={12} sm={3}>
            <TextField
              fullWidth
              label="Interface IP"
              value={interfaceIp}
              onChange={(e) => setInterfaceIp(e.target.value)}
              helperText="Optional local IP to bind"
            />
          </Grid>

          {/* Scan Button */}
          <Grid item xs={12} sm={2}>
            <Button
              variant="contained"
              color="primary"
              fullWidth
              onClick={fetchDevices}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : "Scan"}
            </Button>
          </Grid>
        </Grid>

        {/* Toggles & Actions */}
        <Grid container spacing={2} style={{ marginTop: "20px" }}>
          <Grid item xs={12} sm={3}>
            <FormControlLabel
              control={<Switch checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />}
              label="Show Raw JSON"
            />
          </Grid>
          <Grid item xs={12} sm={3}>
            <Button variant="outlined" fullWidth onClick={exportJson} disabled={!Object.keys(devices).length}>
              Export JSON
            </Button>
          </Grid>
          <Grid item xs={12} sm={3}>
            <Button variant="outlined" fullWidth onClick={exportCsv} disabled={!Object.keys(devices).length}>
              Export CSV
            </Button>
          </Grid>
        </Grid>

        {/* Device List */}
        <div style={{ marginTop: "40px" }}>
          {Object.keys(devices).length === 0 ? (
            <Typography variant="h6" align="center">
              No devices found. Click "Scan" to start discovery.
            </Typography>
          ) : (
            Object.entries(devices).map(([proto, deviceList]) => (
              <div key={proto}>
                <Typography variant="h5" style={{ marginTop: "20px" }}>
                  {proto.toUpperCase()} Devices ({deviceList.length})
                </Typography>
                <Grid container spacing={2}>
                  {deviceList.map((device, index) => (
                    <Grid item xs={12} sm={6} md={4} key={index}>
                      <Card variant="outlined" className="device-card">
                        <CardContent className="card-content">
                          <Typography variant="subtitle1">
                            <strong>Name:</strong>{" "}
                            {device.name ? device.name : "N/A"}
                          </Typography>
                          <Typography variant="body2">
                            <strong>Type:</strong>{" "}
                            {device.type
                              ? device.type
                              : device.ST
                              ? device.ST
                              : "N/A"}
                          </Typography>
                          {device.address && (
                            <Typography variant="body2">
                              <strong>Address:</strong> {device.address}
                            </Typography>
                          )}
                          {device.LOCATION && (
                            <Typography variant="body2">
                              <strong>Location:</strong> {device.LOCATION}
                            </Typography>
                          )}
                          {device.USN && (
                            <Typography variant="body2">
                              <strong>USN:</strong> {device.USN}
                            </Typography>
                          )}
                          {device.SERVER && (
                            <Typography variant="body2">
                              <strong>Server:</strong> {device.SERVER}
                            </Typography>
                          )}
                          {device.response && (
                            <Typography variant="body2" className="long-text">
                              <strong>Response:</strong> {device.response}
                            </Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </div>
            ))
          )}
        </div>

        {showRaw && (
          <pre style={{ marginTop: 20, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {JSON.stringify(devices, null, 2)}
          </pre>
        )}

        <Snackbar open={!!error} autoHideDuration={6000} onClose={() => setError("")}>
          <Alert onClose={() => setError("")} severity="error" sx={{ width: "100%" }}>
            {error}
          </Alert>
        </Snackbar>
      </Container>
    </ThemeProvider>
  );
}

export default App;
