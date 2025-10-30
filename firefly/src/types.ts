export type ProtocolKey = 'upnp' | 'mdns' | 'wsd';

export interface UPnPDevice {
  address?: string;
  name?: string;
  type?: string;
  LOCATION?: string;
  USN?: string;
  SERVER?: string;
  ST?: string;
}

export interface MDNSService {
  name?: string;
  type?: string;
  addresses?: string[];
  port?: number;
  properties?: Record<string, string> | undefined;
}

export interface WSDDevice {
  address: string;
  response: string;
}

export interface DiscoverResponse {
  upnp: UPnPDevice[];
  mdns: MDNSService[];
  wsd: WSDDevice[];
}
