export type ProtocolKey = 'upnp' | 'mdns' | 'wsd' | 'mqtt' | 'coap';

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

export interface MQTTBroker {
  address: string;
  port: number;
  broker_name?: string;
  broker_version?: string;
  anonymous_access: boolean;
  tls_supported: boolean;
  anonymous_publish: boolean;
  connected_clients?: number;
  uptime_seconds?: number;
  messages_received?: number;
  messages_sent?: number;
  sampled_topics: string[];
  topic_count: number;
  risk_flags: string[];
  metadata: Record<string, unknown>;
  fingerprint?: DeviceFingerprint;
}

export interface CoAPResource {
  uri: string;
  rt?: string;
  if_desc?: string;
  ct?: string;
  observable: boolean;
  title?: string;
}

export interface CoAPDevice {
  address: string;
  port: number;
  resources: CoAPResource[];
  device_type?: string;
  firmware?: string;
  dtls_supported: boolean;
  unauthenticated_access: boolean;
  observable_resources: string[];
  risk_flags: string[];
  metadata: Record<string, unknown>;
  fingerprint?: DeviceFingerprint;
}

export interface DiscoverResponse {
  upnp: UPnPDevice[];
  mdns: MDNSService[];
  wsd: WSDDevice[];
  mqtt: MQTTBroker[];
  coap: CoAPDevice[];
}
