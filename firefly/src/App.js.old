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

// Use an environment variable for the API URL or default to localhost.
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

function App() {
  // Existing state variables
  const [devices, setDevices] = useState({});
  const [loading, setLoading] = useState(false);
  const [protocol, setProtocol] = useState("all");
  const [timeoutVal, setTimeoutVal] = useState(5);
  const [mdnsService, setMdnsService] = useState("_services._dns-sd._udp.local.");

  // New state variables for UPnP options
  const [upnpST, setUpnpST] = useState("ssdp:all");
  const [upnpMX, setUpnpMX] = useState(3);
  const [upnpTTL, setUpnpTTL] = useState(2);

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

  // Fetch on component mount (optional)
  useEffect(() => {
    fetchDevices();
  }, []);

  return (
    <Container style={{ marginTop: "20px", marginBottom: "40px" }}>
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

        {/* UPnP Fields: Only show when protocol is "all" or "upnp" */}
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

      {/* Display the discovered devices */}
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
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1">
                          <strong>Name:</strong>{" "}
                          {device.name ? device.name : "N/A"}
                        </Typography>
                        <Typography variant="body2">
                          <strong>Type:</strong>{" "}
                          {device.type ? device.type : "N/A"}
                        </Typography>
                        {device.address && (
                          <Typography variant="body2">
                            <strong>Address:</strong> {device.address}
                          </Typography>
                        )}
                        {device.port && (
                          <Typography variant="body2">
                            <strong>Port:</strong> {device.port}
                          </Typography>
                        )}
                        {device.properties && (
                          <Typography variant="body2">
                            <strong>Properties:</strong>{" "}
                            {JSON.stringify(device.properties)}
                          </Typography>
                        )}
                        {device.response && (
                          <Typography
                            variant="body2"
                            style={{ wordBreak: "break-all" }}
                          >
                            <strong>Response:</strong>{" "}
                            {device.response.substring(0, 200)}...
                          </Typography>
                        )}
                        {device.queried_service && (
                          <Typography variant="body2">
                            <strong>Queried Service:</strong>{" "}
                            {device.queried_service}
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
  );
}

export default App;
