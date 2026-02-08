import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Snackbar,
  Alert,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  Skeleton,
  Pagination,
  Button,
  IconButton,
  Chip,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import StopIcon from '@mui/icons-material/Stop';
import RouterIcon from '@mui/icons-material/Router';
import DnsIcon from '@mui/icons-material/Dns';
import VideocamIcon from '@mui/icons-material/Videocam';
import SearchIcon from '@mui/icons-material/Search';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { discover } from './api/discover';
import { apiClient } from './api/client';
import type { DiscoverResponse, ProtocolKey, UPnPDevice, MDNSService, WSDDevice } from './types';
import { loadSettings, saveSettings } from './settings';
import './App.css';

/* ----------------------------------------------------------------
   Theme
   ---------------------------------------------------------------- */
const cyberTheme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#050508', paper: '#0f1118' },
    primary: { main: '#00d4ff' },
    secondary: { main: '#ff0066' },
    success: { main: '#00ff88' },
    error: { main: '#ff0066' },
    text: { primary: '#e4e8f1', secondary: '#8891a4' },
  },
  typography: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
  shape: { borderRadius: 10 },
});

/* ----------------------------------------------------------------
   Protocol metadata (used for info cards)
   ---------------------------------------------------------------- */
const PROTOCOLS: {
  key: ProtocolKey;
  name: string;
  port: string;
  description: string;
  discovers: string[];
  Icon: React.ElementType;
}[] = [
  {
    key: 'upnp',
    name: 'UPnP / SSDP',
    port: 'Multicast UDP 1900',
    description:
      'Universal Plug and Play uses SSDP multicast to locate smart TVs, media servers, routers, and IoT gateways. FireFly enriches results by fetching device description XML with SSRF-safe guardrails.',
    discovers: ['Smart TVs', 'Media Servers', 'Routers', 'IoT Gateways'],
    Icon: RouterIcon,
  },
  {
    key: 'mdns',
    name: 'mDNS / Zeroconf',
    port: 'Multicast UDP 5353',
    description:
      'Multicast DNS enables zero-configuration discovery of local services -- printers, AirPlay speakers, Chromecast, and HTTP servers -- without requiring a central DNS server.',
    discovers: ['Printers', 'AirPlay', 'Chromecast', 'Web Services'],
    Icon: DnsIcon,
  },
  {
    key: 'wsd',
    name: 'WS-Discovery',
    port: 'Multicast UDP 3702',
    description:
      'Web Services Discovery sends SOAP/XML probes to find IP cameras (ONVIF), network printers, and enterprise devices commonly found in surveillance and office environments.',
    discovers: ['IP Cameras', 'ONVIF Devices', 'Network Printers'],
    Icon: VideocamIcon,
  },
];

/* ----------------------------------------------------------------
   Constants & helpers
   ---------------------------------------------------------------- */
const API_URL =
  (process.env.REACT_APP_API_URL as string | undefined) ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

const emptyResults: DiscoverResponse = { upnp: [], mdns: [], wsd: [] };
type PageSize = 12 | 24 | 48;

function totalDevices(d: DiscoverResponse): number {
  return d.upnp.length + d.mdns.length + d.wsd.length;
}

/* ----------------------------------------------------------------
   Merge helpers — accumulate results across scans by device identity
   ---------------------------------------------------------------- */

function mergeByKey<T>(existing: T[], incoming: T[], keyFn: (item: T) => string): T[] {
  const map = new Map<string, T>();
  for (const item of existing) {
    map.set(keyFn(item) || JSON.stringify(item), item);
  }
  // Incoming (newer) data overwrites existing entries with the same key
  for (const item of incoming) {
    map.set(keyFn(item) || JSON.stringify(item), item);
  }
  return Array.from(map.values());
}

const upnpKey = (d: UPnPDevice): string => d.USN || `${d.address ?? ''}|${d.LOCATION ?? ''}`;
const mdnsKey = (d: MDNSService): string => d.name || '';
const wsdKey = (d: WSDDevice): string => d.address;

function mergeResults(existing: DiscoverResponse, incoming: DiscoverResponse): DiscoverResponse {
  return {
    upnp: mergeByKey(existing.upnp, incoming.upnp, upnpKey),
    mdns: mergeByKey(existing.mdns, incoming.mdns, mdnsKey),
    wsd: mergeByKey(existing.wsd, incoming.wsd, wsdKey),
  };
}

/* ================================================================
   App
   ================================================================ */
export default function App(): JSX.Element {
  const queryClient = useQueryClient();
  const initial = loadSettings();

  /* ---- Scan parameters ---- */
  const [protocol, setProtocol] = useState<'all' | ProtocolKey>(initial.protocol);
  const [timeoutVal, setTimeoutVal] = useState<number>(initial.timeoutVal);
  const [mdnsService, setMdnsService] = useState<string>(initial.mdnsService);
  const [interfaceIp, setInterfaceIp] = useState<string>(initial.interfaceIp || '');
  const [upnpST, setUpnpST] = useState<string>(initial.upnpST);
  const [upnpMX, setUpnpMX] = useState<number>(initial.upnpMX);
  const [upnpTTL, setUpnpTTL] = useState<number>(initial.upnpTTL);
  const [enrich, setEnrich] = useState<boolean>(initial.enrich);

  /* ---- UI state ---- */
  const [toastMsg, setToastMsg] = useState('');
  const [toastSeverity, setToastSeverity] = useState<'error' | 'success' | 'info'>('error');
  const [showRaw, setShowRaw] = useState(initial.showRaw);
  const [activeTab, setActiveTab] = useState<'all' | ProtocolKey>(initial.activeTab);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(initial.pageSize as PageSize);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [hasScanned, setHasScanned] = useState(false);

  /* ---- Accumulated results (persisted across scans) ---- */
  const [accumulatedResults, setAccumulatedResults] = useState<DiscoverResponse>(emptyResults);
  const [scanCount, setScanCount] = useState(0);

  /* ---- Progress ---- */
  const [progress, setProgress] = useState(0);
  const progressRef = useRef<{ timer: ReturnType<typeof setInterval> | null; start: number }>({
    timer: null,
    start: 0,
  });

  /* ---- Backend health check (runs on mount + every 30 s) ---- */
  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        await apiClient.get('/api/healthz', { timeout: 5000 });
        if (active) setBackendStatus('online');
      } catch {
        if (active) setBackendStatus('offline');
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  /* ---- React Query — discovery ---- */
  // Stable queryKey so changing scan parameters never discards cached results.
  // The actual parameters are captured by the queryFn closure on each render.
  const queryKey = ['discover'] as const;

  const {
    data,
    isFetching,
    isError,
    error: queryError,
    refetch,
    dataUpdatedAt,
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
          enrich: enrich || undefined,
        },
        signal as AbortSignal | undefined,
      ),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  /* ---- Merge incoming scan results into the accumulated set ---- */
  const lastMergedAt = useRef(0);
  useEffect(() => {
    if (data && dataUpdatedAt > lastMergedAt.current) {
      lastMergedAt.current = dataUpdatedAt;
      setAccumulatedResults((prev) => mergeResults(prev, data));
      setScanCount((c) => c + 1);
      const incoming = totalDevices(data);
      if (incoming > 0) {
        showToast(`Scan complete — ${incoming} device${incoming !== 1 ? 's' : ''} found`, 'success');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, dataUpdatedAt]);

  const devices: DiscoverResponse = accumulatedResults;
  const deviceCount = totalDevices(devices);

  /* ---- Surface query errors ---- */
  useEffect(() => {
    if (isError && queryError) {
      const msg =
        (queryError as any)?.response?.data?.detail || // eslint-disable-line @typescript-eslint/no-explicit-any
        (queryError as any)?.message || // eslint-disable-line @typescript-eslint/no-explicit-any
        'Discovery request failed';
      showToast(msg, 'error');
    }
  }, [isError, queryError]);

  /* ---- Determinate progress bar ---- */
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
      const t = setTimeout(() => setProgress(0), 400);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFetching]);

  /* ---- Persist UI prefs ---- */
  useEffect(() => {
    saveSettings({ showRaw, activeTab, pageSize, enrich });
  }, [showRaw, activeTab, pageSize, enrich]);

  /* ---- Derived data ---- */
  const counts = { upnp: devices.upnp.length, mdns: devices.mdns.length, wsd: devices.wsd.length };

  const protocolTabs: { key: 'all' | ProtocolKey; label: string }[] = [
    { key: 'all', label: `All (${deviceCount})` },
    { key: 'upnp', label: `UPnP (${counts.upnp})` },
    { key: 'mdns', label: `mDNS (${counts.mdns})` },
    { key: 'wsd', label: `WSD (${counts.wsd})` },
  ];

  const entriesAll =
    activeTab === 'all'
      ? (Object.entries(devices) as [ProtocolKey, any[]][]).flatMap( // eslint-disable-line @typescript-eslint/no-explicit-any
          ([proto, list]) => (list || []).map((d: any) => ({ proto, device: d })), // eslint-disable-line @typescript-eslint/no-explicit-any
        )
      : (devices[activeTab] || []).map((d: any) => ({ proto: activeTab, device: d })); // eslint-disable-line @typescript-eslint/no-explicit-any

  const q = search.trim().toLowerCase();
  const filteredEntries = q
    ? entriesAll.filter(({ device }) => JSON.stringify(device).toLowerCase().includes(q))
    : entriesAll;

  const pageCount = Math.max(1, Math.ceil(filteredEntries.length / pageSize));
  const pagedEntries = filteredEntries.slice((page - 1) * pageSize, page * pageSize);

  /* ---- Actions ---- */
  const startScan = () => {
    setPage(1);
    setHasScanned(true);
    saveSettings({ protocol, timeoutVal, mdnsService, upnpST, upnpMX, upnpTTL, interfaceIp });
    refetch();
  };

  const cancelScan = async () => {
    try {
      await queryClient.cancelQueries({ queryKey });
      showToast('Scan cancelled', 'info');
    } catch {
      /* noop */
    }
  };

  const clearResults = useCallback(() => {
    setAccumulatedResults(emptyResults);
    setScanCount(0);
    setHasScanned(false);
    setPage(1);
    queryClient.removeQueries({ queryKey });
    showToast('Results cleared', 'info');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient]);

  const showToast = (msg: string, severity: 'error' | 'success' | 'info' = 'error') => {
    setToastMsg(msg);
    setToastSeverity(severity);
  };

  const copyText = (text: string) => {
    navigator.clipboard?.writeText(text).then(() => showToast('Copied to clipboard', 'success'));
  };

  /* ---- Export helpers ---- */
  const downloadFile = (filename: string, content: string) => {
    const el = document.createElement('a');
    el.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(content));
    el.setAttribute('download', filename);
    el.style.display = 'none';
    document.body.appendChild(el);
    el.click();
    document.body.removeChild(el);
  };

  const exportJson = () => downloadFile('firefly_results.json', JSON.stringify(devices, null, 2));

  const exportCsv = () => {
    try {
      const rows: Record<string, unknown>[] = [];
      (Object.entries(devices) as [string, any[]][]).forEach(([proto, list]) => // eslint-disable-line @typescript-eslint/no-explicit-any
        list.forEach((d: any) => rows.push({ protocol: proto, ...d })), // eslint-disable-line @typescript-eslint/no-explicit-any
      );
      if (!rows.length) return;
      const headers = Array.from(
        rows.reduce((set, row) => {
          Object.keys(row).forEach((k) => set.add(k));
          return set;
        }, new Set<string>()),
      );
      const csv = [headers.join(',')]
        .concat(rows.map((r: any) => headers.map((h) => JSON.stringify(r[h] ?? '')).join(','))) // eslint-disable-line @typescript-eslint/no-explicit-any
        .join('\n');
      downloadFile('firefly_results.csv', csv);
    } catch {
      showToast('Export failed');
    }
  };

  /* ---- Render a single device card ---- */
  const renderDeviceCard = (proto: ProtocolKey, device: any, index: number) => { // eslint-disable-line @typescript-eslint/no-explicit-any
    const fp = device.fingerprint;
    const name = fp?.manufacturer && fp?.model
      ? `${fp.manufacturer} ${fp.model}`
      : device.name || device.friendlyName || 'Unknown Device';
    const type = device.type || device.ST || device.deviceType || '';
    const category: string | undefined = fp?.device_category;
    const tags: string[] = fp?.device_tags || [];
    const services: any[] = fp?.services || []; // eslint-disable-line @typescript-eslint/no-explicit-any
    const banners: Record<string, string> = fp?.banners || {};

    return (
      <div className="result-card" key={`${proto}-${index}`} style={{ animationDelay: `${index * 40}ms` }}>
        <div className={`result-card-accent ${proto}`} />
        <div className="result-card-body">
          {/* Header: name + badges */}
          <div className="result-card-header">
            <div>
              <div className="result-device-name">{name}</div>
              {type && <div className="result-device-type">{type}</div>}
            </div>
            <div style={{ display: 'flex', gap: 4, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {category && category !== 'unknown' && (
                <span className={`category-badge category-${category}`}>{category}</span>
              )}
              <span className={`result-protocol-badge ${proto}`}>{proto}</span>
            </div>
          </div>

          {/* Fingerprint summary (when enriched) */}
          {fp && (
            <div className="fingerprint-summary">
              {fp.manufacturer && <span className="fp-chip">{fp.manufacturer}</span>}
              {fp.model && <span className="fp-chip">{fp.model}</span>}
              {fp.firmware_version && <span className="fp-chip">FW {fp.firmware_version}</span>}
              {fp.os_guess && <span className="fp-chip fp-chip--os">{fp.os_guess}</span>}
              {services.length > 0 && <span className="fp-chip fp-chip--svc">{services.length} services</span>}
            </div>
          )}

          {/* Tags */}
          {tags.length > 0 && (
            <div className="fingerprint-tags">
              {tags.map((t) => <span className="fp-tag" key={t}>{t}</span>)}
            </div>
          )}

          {/* Fields */}
          <div className="result-fields">
            {device.address && (
              <div className="result-field">
                <span className="result-field-label">Addr</span>
                <span className="result-field-value">{device.address}</span>
                <IconButton size="small" className="result-copy-btn" onClick={() => copyText(device.address)}>
                  <ContentCopyIcon sx={{ fontSize: 13 }} />
                </IconButton>
              </div>
            )}

            {device.addresses && device.addresses.length > 0 && (
              <div className="result-field">
                <span className="result-field-label">IPs</span>
                <span className="result-field-value">{device.addresses.join(', ')}</span>
              </div>
            )}

            {device.port != null && (
              <div className="result-field">
                <span className="result-field-label">Port</span>
                <span className="result-field-value">{device.port}</span>
              </div>
            )}

            {device.LOCATION && (
              <div className="result-field">
                <span className="result-field-label">Loc</span>
                <span className="result-field-value">{device.LOCATION}</span>
                <IconButton size="small" className="result-copy-btn" onClick={() => copyText(device.LOCATION)}>
                  <ContentCopyIcon sx={{ fontSize: 13 }} />
                </IconButton>
              </div>
            )}

            {fp?.device_url && !device.LOCATION && (
              <div className="result-field">
                <span className="result-field-label">URL</span>
                <span className="result-field-value">{fp.device_url}</span>
                <IconButton size="small" className="result-copy-btn" onClick={() => copyText(fp.device_url)}>
                  <ContentCopyIcon sx={{ fontSize: 13 }} />
                </IconButton>
              </div>
            )}

            {fp?.serial_number && (
              <div className="result-field">
                <span className="result-field-label">S/N</span>
                <span className="result-field-value">{fp.serial_number}</span>
              </div>
            )}

            {device.USN && (
              <div className="result-field">
                <span className="result-field-label">USN</span>
                <span className="result-field-value">{device.USN}</span>
              </div>
            )}

            {device.SERVER && (
              <div className="result-field">
                <span className="result-field-label">Srv</span>
                <span className="result-field-value">{device.SERVER}</span>
              </div>
            )}
          </div>

          {/* Expandable: Services (from enrichment) */}
          {services.length > 0 && (
            <details className="result-expandable">
              <summary>Services ({services.length})</summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                {services.map((svc: any, i: number) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
                  <div className="result-field" key={i}>
                    <span className="result-field-label" style={{ minWidth: 'auto' }}>
                      :{svc.port}
                    </span>
                    <span className="result-field-value">
                      {svc.name}{svc.tls ? ' (TLS)' : ''}{svc.banner ? ` — ${svc.banner.slice(0, 80)}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Expandable: Banners (from enrichment) */}
          {Object.keys(banners).length > 0 && (
            <details className="result-expandable">
              <summary>Banners ({Object.keys(banners).length})</summary>
              {Object.entries(banners).map(([port, banner]) => (
                <div key={port} style={{ marginTop: 6 }}>
                  <div className="result-field-label" style={{ marginBottom: 2 }}>Port {port}</div>
                  <pre>{banner}</pre>
                </div>
              ))}
            </details>
          )}

          {/* Expandable: mDNS properties */}
          {device.properties && Object.keys(device.properties).length > 0 && (
            <details className="result-expandable">
              <summary>Properties ({Object.keys(device.properties).length})</summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 8 }}>
                {Object.entries(device.properties).map(([k, v]) => (
                  <div className="result-field" key={k}>
                    <span className="result-field-label" style={{ minWidth: 'auto' }}>{k}</span>
                    <span className="result-field-value">{String(v)}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Expandable: WSD raw response */}
          {device.response && (
            <details className="result-expandable">
              <summary>Raw XML Response</summary>
              <pre>{device.response}</pre>
            </details>
          )}
        </div>
      </div>
    );
  };

  /* ================================================================
     RENDER
     ================================================================ */
  return (
    <ThemeProvider theme={cyberTheme}>
      <div className="cyber-app">
        {/* ============================================================
            HEADER
            ============================================================ */}
        <header className="cyber-header">
          <h1 className="cyber-title">FIREFLY</h1>
          <p className="cyber-subtitle">IoT Device Discovery Platform</p>
          <p className="cyber-tagline">
            Multi-protocol network scanner for discovering IoT devices using UPnP, mDNS,
            and WS-Discovery with enterprise-grade SSRF protection, rate limiting,
            and optional API key authentication.
          </p>
          <div
            className={`status-badge ${backendStatus}`}
            title={
              backendStatus === 'online'
                ? 'Backend API is reachable'
                : backendStatus === 'offline'
                  ? 'Cannot reach backend API'
                  : 'Checking connectivity...'
            }
          >
            <span className="status-dot" />
            {backendStatus === 'online' && 'API Online'}
            {backendStatus === 'offline' && 'API Offline'}
            {backendStatus === 'checking' && 'Checking...'}
          </div>
        </header>

        {/* ============================================================
            PROTOCOL INFO
            ============================================================ */}
        <section className="protocol-section">
          <div className="section-label">Discovery Protocols</div>
          <div className="protocol-grid">
            {PROTOCOLS.map((p) => (
              <div className={`protocol-card ${p.key}`} key={p.key}>
                <div className="protocol-card-header">
                  <div className="protocol-icon">
                    <p.Icon />
                  </div>
                  <div>
                    <div className="protocol-name">{p.name}</div>
                    <div className="protocol-port">{p.port}</div>
                  </div>
                </div>
                <p className="protocol-desc">{p.description}</p>
                <div className="protocol-tags">
                  {p.discovers.map((tag) => (
                    <span className="protocol-tag" key={tag}>{tag}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ============================================================
            SCAN PANEL
            ============================================================ */}
        <section className="scan-panel">
          <div className="section-label">Scan Configuration</div>

          <div className="scan-controls">
            <FormControl fullWidth size="small">
              <InputLabel>Protocol</InputLabel>
              <Select
                value={protocol}
                label="Protocol"
                onChange={(e) => setProtocol(e.target.value as 'all' | ProtocolKey)}
              >
                <MenuItem value="all">All Protocols</MenuItem>
                <MenuItem value="upnp">UPnP / SSDP</MenuItem>
                <MenuItem value="mdns">mDNS / Zeroconf</MenuItem>
                <MenuItem value="wsd">WS-Discovery</MenuItem>
              </Select>
            </FormControl>

            <TextField
              fullWidth
              size="small"
              type="number"
              label="Timeout (seconds)"
              value={timeoutVal}
              onChange={(e) => setTimeoutVal(Math.max(1, Math.min(300, Number(e.target.value) || 1)))}
              helperText="1 - 300s"
            />

            {(protocol === 'all' || protocol === 'mdns') && (
              <TextField
                fullWidth
                size="small"
                label="mDNS Service Type"
                value={mdnsService}
                onChange={(e) => setMdnsService(e.target.value)}
                helperText='"all" or e.g. _http._tcp.local.'
              />
            )}

            {(protocol === 'all' || protocol === 'upnp') && (
              <>
                <TextField
                  fullWidth
                  size="small"
                  label="UPnP Search Target"
                  value={upnpST}
                  onChange={(e) => setUpnpST(e.target.value)}
                  helperText="e.g. ssdp:all"
                />
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="UPnP MX"
                  value={upnpMX}
                  onChange={(e) => setUpnpMX(Number(e.target.value))}
                  helperText="Max wait 1-5"
                />
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="Multicast TTL"
                  value={upnpTTL}
                  onChange={(e) => setUpnpTTL(Number(e.target.value))}
                  helperText="Hop limit 1-16"
                />
              </>
            )}

            <TextField
              fullWidth
              size="small"
              label="Interface IP"
              value={interfaceIp}
              onChange={(e) => setInterfaceIp(e.target.value)}
              helperText="Optional bind address"
            />
          </div>

          <div className="scan-actions">
            {!isFetching ? (
              <button
                className="scan-btn"
                onClick={startScan}
                disabled={backendStatus === 'offline'}
              >
                {enrich ? 'Deep Scan' : 'Initiate Scan'}
              </button>
            ) : (
              <button className="scan-btn scan-btn--cancel" onClick={cancelScan}>
                <StopIcon sx={{ fontSize: 18 }} />
                Cancel Scan
              </button>
            )}
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={enrich}
                  onChange={(e) => setEnrich(e.target.checked)}
                />
              }
              label={
                <span className="enrich-label">
                  Deep Scan
                  <span className="enrich-hint">
                    Fingerprint, banner grab, classify
                  </span>
                </span>
              }
            />
            {deviceCount > 0 && (
              <>
                <Chip
                  label={`${deviceCount} device${deviceCount !== 1 ? 's' : ''} from ${scanCount} scan${scanCount !== 1 ? 's' : ''}`}
                  size="small"
                  sx={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.7rem',
                    letterSpacing: '0.5px',
                    color: 'var(--text-secondary)',
                    borderColor: 'var(--border)',
                  }}
                  variant="outlined"
                />
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteSweepIcon sx={{ fontSize: 16 }} />}
                  onClick={clearResults}
                  sx={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.7rem',
                    textTransform: 'uppercase',
                    letterSpacing: '1px',
                  }}
                >
                  Clear
                </Button>
              </>
            )}
          </div>

          {isFetching && (
            <div className="scan-progress">
              <div className="scan-progress-text scanning-text">
                Scanning {protocol === 'all' ? 'all protocols' : protocol.toUpperCase()}
                {' \u2014 '}
                ~{Math.max(0, Math.ceil(timeoutVal * (100 - progress) / 100))}s remaining
              </div>
              <div className="scan-progress-bar">
                <div className="scan-progress-fill" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
        </section>

        {/* ============================================================
            RESULTS
            ============================================================ */}
        <section className="results-section">
          <div className="section-label">Discovery Results</div>

          <Tabs
            value={activeTab}
            onChange={(_, v) => {
              setActiveTab(v);
              setPage(1);
              saveSettings({ activeTab: v });
            }}
            aria-label="Protocol result tabs"
            variant="scrollable"
            scrollButtons="auto"
          >
            {protocolTabs.map((t) => (
              <Tab key={t.key} value={t.key} label={t.label} />
            ))}
          </Tabs>

          <div className="results-toolbar">
            <TextField
              className="search-field"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              label="Search results"
              placeholder="Filter by name, address, type..."
              size="small"
              InputProps={{
                startAdornment: (
                  <SearchIcon sx={{ mr: 1, color: 'var(--text-muted)', fontSize: 18 }} />
                ),
              }}
            />
            <FormControl size="small" sx={{ minWidth: 110 }}>
              <InputLabel>Per page</InputLabel>
              <Select
                label="Per page"
                value={pageSize}
                onChange={(e) => {
                  const v = Number(e.target.value) as PageSize;
                  setPageSize(v);
                  setPage(1);
                }}
              >
                {[12, 24, 48].map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </div>

          {/* Error state */}
          {isError && !isFetching && (
            <div className="error-state">
              <div className="error-state-title">Discovery Failed</div>
              <div className="error-state-desc">
                {(queryError as any)?.response?.data?.detail || /* eslint-disable-line @typescript-eslint/no-explicit-any */
                  (queryError as any)?.message || /* eslint-disable-line @typescript-eslint/no-explicit-any */
                  'Could not reach the backend API. Ensure the backend is running and accessible.'}
              </div>
            </div>
          )}

          {/* Loading skeletons */}
          {isFetching && (
            <div className="skeleton-grid">
              {Array.from({ length: 6 }).map((_, i) => (
                <div className="skeleton-card" key={i}>
                  <Skeleton variant="text" width="60%" />
                  <Skeleton variant="text" width="40%" />
                  <Skeleton variant="rectangular" height={60} sx={{ borderRadius: 1, mt: 1 }} />
                </div>
              ))}
            </div>
          )}

          {/* Empty: no scan yet */}
          {!isFetching && !hasScanned && !isError && (
            <div className="empty-state">
              <div className="empty-state-icon">
                <SearchIcon sx={{ fontSize: 'inherit' }} />
              </div>
              <div className="empty-state-title">Ready to Discover</div>
              <div className="empty-state-desc">
                Configure your scan parameters above and click &ldquo;Initiate Scan&rdquo; to probe
                your local network for IoT devices across all supported protocols.
              </div>
            </div>
          )}

          {/* Empty: scanned but 0 devices */}
          {!isFetching && hasScanned && deviceCount === 0 && !isError && (
            <div className="empty-state">
              <div className="empty-state-icon">
                <SearchIcon sx={{ fontSize: 'inherit' }} />
              </div>
              <div className="empty-state-title">No Devices Found</div>
              <div className="empty-state-desc">
                The scan completed but no devices were discovered. This can happen in certain
                network configurations, especially in containerized environments.
              </div>
              <div className="empty-state-hint">
                Troubleshooting tips:
                <br />
                - Increase the timeout for slower networks
                <br />
                - Try scanning individual protocols
                <br />
                - If running in Docker, multicast is limited &mdash;
                use <code>--network host</code> (Linux) or run backend on the host
                <br />
                - Ensure your firewall allows UDP multicast traffic
                <br />
                - Try specifying your network interface IP
              </div>
            </div>
          )}

          {/* Results grid */}
          {!isFetching && deviceCount > 0 && (
            <>
              <div className="results-count">
                Showing {pagedEntries.length} of {filteredEntries.length} device
                {filteredEntries.length !== 1 ? 's' : ''}
                {search && ` matching "${search}"`}
              </div>
              <div className="results-grid">
                {pagedEntries.map(({ proto, device }, i) => renderDeviceCard(proto, device, i))}
              </div>
              {pageCount > 1 && (
                <div className="pagination-wrap">
                  <Pagination
                    count={pageCount}
                    page={page}
                    onChange={(_, p) => setPage(p)}
                    color="primary"
                    showFirstButton
                    showLastButton
                  />
                </div>
              )}
            </>
          )}
        </section>

        {/* ============================================================
            FOOTER TOOLBAR
            ============================================================ */}
        <div className="footer-bar">
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={showRaw}
                onChange={(e) => setShowRaw(e.target.checked)}
              />
            }
            label={
              <span
                style={{
                  fontSize: '0.75rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-secondary)',
                  letterSpacing: '1px',
                  textTransform: 'uppercase',
                }}
              >
                Raw JSON
              </span>
            }
          />
          <Button
            className="footer-btn"
            variant="outlined"
            size="small"
            onClick={exportJson}
            disabled={deviceCount === 0}
          >
            Export JSON
          </Button>
          <Button
            className="footer-btn"
            variant="outlined"
            size="small"
            onClick={exportCsv}
            disabled={deviceCount === 0}
          >
            Export CSV
          </Button>
          <Button
            className="footer-btn"
            variant="outlined"
            size="small"
            component="a"
            href={`${API_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />}
          >
            API Docs
          </Button>
        </div>

        {showRaw && deviceCount > 0 && (
          <div className="raw-json">{JSON.stringify(devices, null, 2)}</div>
        )}

        {/* ============================================================
            TOAST
            ============================================================ */}
        <Snackbar
          open={!!toastMsg}
          autoHideDuration={4000}
          onClose={() => setToastMsg('')}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert
            onClose={() => setToastMsg('')}
            severity={toastSeverity}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {toastMsg}
          </Alert>
        </Snackbar>
      </div>
    </ThemeProvider>
  );
}
