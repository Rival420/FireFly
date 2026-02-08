export type ProtocolKey = 'upnp' | 'mdns' | 'wsd';

/* ----------------------------------------------------------------
   Fingerprint / enrichment types (populated when enrich=true)
   ---------------------------------------------------------------- */

export interface ServiceInfo {
  port: number;
  name: string;
  banner?: string;
  tls?: boolean;
  tls_version?: string;
}

export interface DeviceFingerprint {
  manufacturer?: string;
  model?: string;
  firmware_version?: string;
  serial_number?: string;
  device_url?: string;
  device_category?: string;
  device_tags?: string[];
  os_guess?: string;
  services?: ServiceInfo[];
  banners?: Record<string, string>;
}

/* ----------------------------------------------------------------
   Per-protocol device types
   ---------------------------------------------------------------- */

export interface UPnPDevice {
  address?: string;
  name?: string;
  type?: string;
  LOCATION?: string;
  USN?: string;
  SERVER?: string;
  ST?: string;
  fingerprint?: DeviceFingerprint;
}

export interface MDNSService {
  name?: string;
  type?: string;
  addresses?: string[];
  port?: number;
  properties?: Record<string, string> | undefined;
  fingerprint?: DeviceFingerprint;
}

export interface WSDDevice {
  address: string;
  response: string;
  fingerprint?: DeviceFingerprint;
}

export interface DiscoverResponse {
  upnp: UPnPDevice[];
  mdns: MDNSService[];
  wsd: WSDDevice[];
}
