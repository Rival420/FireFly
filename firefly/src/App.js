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

  // General discovery settings.
  const [protocol, setProtocol] = useState("all");
  const [timeoutVal, setTimeoutVal] = useState(5);
  const [mdnsService, setMdnsService] = useState("_services._dns-sd._udp.local.");

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
        },
      });
      setDevices(response.data);
    } catch (error) {
      console.error("Error fetching devices:", error);
    } finally {
      setLoading(false);
    }
  };

  // Optionally auto-fetch on mount.
  useEffect(() => {
    // fetchDevices();
  }, []);

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
      </Container>
    </ThemeProvider>
  );
}

export default App;
