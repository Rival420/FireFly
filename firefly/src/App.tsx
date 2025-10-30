import React, { useState, useEffect, useRef } from 'react';
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
  Tabs,
  Tab,
  Skeleton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  LinearProgress,
  Pagination,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { discover } from './api/discover';
import type { DiscoverResponse, ProtocolKey } from './types';
import { loadSettings, saveSettings } from './settings';
import './App.css';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#121212', paper: '#1d1d1d' },
    primary: { main: '#90caf9' },
    text: { primary: '#ffffff' },
  },
});

const API_URL =
  (process.env.REACT_APP_API_URL as string | undefined) ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

const emptyResults: DiscoverResponse = { upnp: [], mdns: [], wsd: [] };

type PageSize = 12 | 24 | 48;

export default function App(): JSX.Element {
  const queryClient = useQueryClient();

  // Initialize from typed settings
  const initial = loadSettings();

  const [protocol, setProtocol] = useState<'all' | ProtocolKey>(initial.protocol);
  const [timeoutVal, setTimeoutVal] = useState<number>(initial.timeoutVal);
  const [mdnsService, setMdnsService] = useState<string>(initial.mdnsService);
  const [interfaceIp, setInterfaceIp] = useState<string>(initial.interfaceIp || '');
  const [upnpST, setUpnpST] = useState<string>(initial.upnpST);
  const [upnpMX, setUpnpMX] = useState<number>(initial.upnpMX);
  const [upnpTTL, setUpnpTTL] = useState<number>(initial.upnpTTL);

  const [error, setError] = useState<string>('');
  const [showRaw, setShowRaw] = useState<boolean>(initial.showRaw);
  const [activeTab, setActiveTab] = useState<'all' | ProtocolKey>(initial.activeTab);
  const [search, setSearch] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<PageSize>(initial.pageSize as PageSize);

  // Progress state
  const [progress, setProgress] = useState<number>(0);
  const progressRef = useRef<{ timer: ReturnType<typeof setInterval> | null; start: number }>({ timer: null, start: 0 });

  // React Query for discovery (disabled by default; trigger via refetch)
  const queryKey = [
    'discover',
    { protocol, timeoutVal, mdnsService, upnpST, upnpMX, upnpTTL, interfaceIp },
  ] as const;

  const {
    data,
    isFetching,
    refetch,
  } = useQuery<DiscoverResponse>({
    queryKey,
    enabled: false,
    queryFn: ({ signal }) =>
      discover(
        {
          protocol,
          timeout: timeoutVal,
          mdns_service: mdnsService,
          upnp_st: upnpST,
          upnp_mx: upnpMX,
          upnp_ttl: upnpTTL,
          interface_ip: interfaceIp || undefined,
        },
        signal as AbortSignal | undefined
      ),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });

  const devices: DiscoverResponse = data ?? emptyResults;

  // Start progress timer when fetching
  useEffect(() => {
    if (isFetching) {
      setProgress(0);
      progressRef.current.start = Date.now();
      if (progressRef.current.timer) clearInterval(progressRef.current.timer);
      progressRef.current.timer = setInterval(() => {
        const elapsedMs = Date.now() - progressRef.current.start;
        const pct = Math.min(99, (elapsedMs / (Math.max(1, timeoutVal) * 1000)) * 100);
        setProgress(pct);
      }, 100);
    } else {
      if (progressRef.current.timer) {
        clearInterval(progressRef.current.timer);
        progressRef.current.timer = null;
      }
      if (progress > 0 && progress < 100) setProgress(100);
      setTimeout(() => setProgress(0), 400);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFetching]);

  // Persist UI prefs on change (typed)
  useEffect(() => {
    saveSettings({ showRaw, activeTab, pageSize });
  }, [showRaw, activeTab, pageSize]);

  const counts = {
    upnp: devices.upnp.length,
    mdns: devices.mdns.length,
    wsd: devices.wsd.length,
  };

  const protocolOrder: { key: 'all' | ProtocolKey; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'upnp', label: `UPnP (${counts.upnp})` },
    { key: 'mdns', label: `mDNS (${counts.mdns})` },
    { key: 'wsd', label: `WS-Discovery (${counts.wsd})` },
  ];

  const filterDevices = <T extends object>(list: T[]): T[] => {
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter((d) => JSON.stringify(d).toLowerCase().includes(q));
  };

  const entriesAll =
    activeTab === 'all'
      ? (Object.entries(devices) as [ProtocolKey, any[]][]) // eslint-disable-line @typescript-eslint/no-explicit-any
          .flatMap(([proto, list]) => (list || []).map((d) => ({ proto, device: d })))
      : (devices[activeTab] || []).map((d) => ({ proto: activeTab, device: d }));

  const filteredEntries = entriesAll.filter(({ device }) => filterDevices([device]).length);
  const pageCount = Math.max(1, Math.ceil(filteredEntries.length / pageSize));
  const pagedEntries = filteredEntries.slice((page - 1) * pageSize, (page - 1) * pageSize + pageSize);

  const cancelScan = async () => {
    try {
      await queryClient.cancelQueries({ queryKey });
      setError('Scan cancelled');
    } catch {}
  };

  const download = (filename: string, text: string) => {
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
    element.setAttribute('download', filename);
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const exportJson = () => download('firefly_results.json', JSON.stringify(devices, null, 2));
  const exportCsv = () => {
    try {
      const rows: Record<string, unknown>[] = [];
      (Object.entries(devices) as [string, any[]][]) // eslint-disable-line @typescript-eslint/no-explicit-any
        .forEach(([proto, list]) => list.forEach((d) => rows.push({ proto, ...d })));
      if (!rows.length) return;
      const headers = Array.from(
        rows.reduce((set, row) => {
          Object.keys(row).forEach((k) => set.add(k));
          return set;
        }, new Set<string>())
      );
      const csv = [headers.join(',')]
        .concat(rows.map((r) => headers.map((h) => JSON.stringify((r as any)[h] ?? '')).join(',')))
        .join('\n');
      download('firefly_results.csv', csv);
    } catch {
      setError('Export failed');
    }
  };

  return (
    <ThemeProvider theme={darkTheme}>
      <Container className="app-container">
        <Typography variant="h3" align="center" gutterBottom>
          Firefly - IoT Device Discovery
        </Typography>

        <Grid container spacing={2} justifyContent="center" alignItems="center">
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth>
              <InputLabel id="protocol-label">Protocol</InputLabel>
              <Select
                labelId="protocol-label"
                value={protocol}
                label="Protocol"
                onChange={(e) => setProtocol(e.target.value as any)}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="upnp">UPnP</MenuItem>
                <MenuItem value="mdns">mDNS</MenuItem>
                <MenuItem value="wsd">WS-Discovery</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          {(protocol === 'all' || protocol === 'mdns') && (
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

          {(protocol === 'all' || protocol === 'upnp') && (
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

          <Grid item xs={12} sm={2}>
            <TextField
              fullWidth
              type="number"
              label="Timeout (s)"
              value={timeoutVal}
              onChange={(e) => setTimeoutVal(Number(e.target.value))}
            />
          </Grid>

          <Grid item xs={12} sm={3}>
            <TextField
              fullWidth
              label="Interface IP"
              value={interfaceIp}
              onChange={(e) => setInterfaceIp(e.target.value)}
              helperText="Optional local IP to bind"
            />
          </Grid>

          <Grid item xs={12} sm={2}>
            <Button
              variant="contained"
              color="primary"
              fullWidth
              onClick={() => { setPage(1); saveSettings({ protocol, timeoutVal, mdnsService, upnpST, upnpMX, upnpTTL, interfaceIp }); refetch(); }}
              disabled={isFetching}
            >
              {isFetching ? <CircularProgress size={24} color="inherit" /> : 'Scan'}
            </Button>
          </Grid>
        </Grid>

        <Grid container spacing={2} style={{ marginTop: '20px' }}>
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
          <Grid item xs={12} sm={3}>
            <Button
              variant="outlined"
              fullWidth
              component="a"
              href={`${API_URL}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open API documentation (Swagger)"
            >
              API Docs (Swagger)
            </Button>
          </Grid>
        </Grid>

        {isFetching && (
          <div style={{ marginTop: 16 }} aria-live="polite">
            <Typography variant="body2" gutterBottom>
              Scanning {protocol.toUpperCase()}… ~{Math.max(0, Math.ceil(timeoutVal * (100 - progress) / 100))}s left
            </Typography>
            <LinearProgress variant="determinate" value={progress} />
            <div className="device-actions">
              <Button size="small" onClick={async () => { await cancelScan(); }} aria-label="Cancel scan">Cancel</Button>
            </div>
          </div>
        )}

        <div style={{ marginTop: '40px' }}>
          <Tabs
            value={activeTab}
            onChange={(_, v) => { setActiveTab(v); setPage(1); saveSettings({ activeTab: v }); }}
            aria-label="Protocol tabs"
          >
            {protocolOrder.map((t) => (
              <Tab key={t.key} value={t.key} label={t.label} />
            ))}
          </Tabs>

          <div className="toolbar-row" role="region" aria-label="Results toolbar">
            <TextField
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              label="Search results"
              inputProps={{ 'aria-label': 'Search results' }}
              placeholder="Search name, type, address, etc."
              fullWidth
            />
            <FormControl size="small" style={{ width: 140 }}>
              <InputLabel id="page-size-label">Page size</InputLabel>
              <Select
                labelId="page-size-label"
                label="Page size"
                value={pageSize}
                onChange={(e) => { const v = Number(e.target.value) as PageSize; setPageSize(v); setPage(1); saveSettings({ pageSize: v }); }}
              >
                {[12, 24, 48].map((s) => (
                  <MenuItem key={s} value={s}>{s}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </div>

          {isFetching && (
            <Grid container spacing={2} style={{ marginTop: 16 }}>
              {Array.from({ length: 6 }).map((_, i) => (
                <Grid item xs={12} sm={6} md={4} key={i}>
                  <Card variant="outlined" className="device-card">
                    <CardContent>
                      <Skeleton variant="text" width="60%" />
                      <Skeleton variant="text" width="40%" />
                      <Skeleton variant="rectangular" height={80} />
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}

          {!isFetching && Object.keys(devices).length === 0 && (
            <Typography variant="h6" align="center">
              No devices found. Click "Scan" to start discovery.
            </Typography>
          )}

          {!isFetching && Object.keys(devices).length > 0 && (
            <Grid container spacing={2}>
              {pagedEntries.map(({ proto, device }, index) => (
                <Grid item xs={12} sm={6} md={4} key={index}>
                  <Accordion>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="subtitle1" style={{ width: '100%' }}>
                        <strong>{device.name || 'Unnamed'}</strong> — {device.type || (device as any).ST || 'Unknown'}
                      </Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Typography variant="body2"><strong>Protocol:</strong> {proto.toUpperCase()}</Typography>
                      {(device as any).address && (
                        <div className="device-actions">
                          <Typography variant="body2"><strong>Address:</strong> {(device as any).address}</Typography>
                          <Button size="small" aria-label={`Copy address ${(device as any).address}`} onClick={() => navigator.clipboard?.writeText((device as any).address)}>Copy</Button>
                        </div>
                      )}
                      {(device as any).LOCATION && (
                        <div className="device-actions">
                          <Typography variant="body2"><strong>Location:</strong> {(device as any).LOCATION}</Typography>
                          <Button size="small" aria-label="Copy LOCATION" onClick={() => navigator.clipboard?.writeText((device as any).LOCATION)}>Copy</Button>
                        </div>
                      )}
                      {(device as any).USN && (
                        <Typography variant="body2"><strong>USN:</strong> {(device as any).USN}</Typography>
                      )}
                      {(device as any).SERVER && (
                        <Typography variant="body2"><strong>Server:</strong> {(device as any).SERVER}</Typography>
                      )}
                      {(device as any).response && (
                        <Typography variant="body2" className="long-text"><strong>Response:</strong> {(device as any).response}</Typography>
                      )}
                    </AccordionDetails>
                  </Accordion>
                </Grid>
              ))}
              <Grid item xs={12}>
                <div className="device-actions" style={{ justifyContent: 'center' }}>
                  <Pagination
                    count={pageCount}
                    page={page}
                    onChange={(_, p) => setPage(p)}
                    color="primary"
                    showFirstButton
                    showLastButton
                    aria-label="Results pagination"
                  />
                </div>
              </Grid>
            </Grid>
          )}
        </div>

        {showRaw && (
          <pre style={{ marginTop: 20, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {JSON.stringify(devices, null, 2)}
          </pre>
        )}

        <Snackbar open={!!error} autoHideDuration={6000} onClose={() => setError('')}>
          <Alert onClose={() => setError('')} severity="error" sx={{ width: '100%' }}>
            {error}
          </Alert>
        </Snackbar>
      </Container>
    </ThemeProvider>
  );
}
