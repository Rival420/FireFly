import { apiClient } from './client';
import type { DiscoverResponse } from '../types';

export interface DiscoverParams {
  protocol?: 'all' | 'upnp' | 'mdns' | 'wsd';
  timeout?: number;
  mdns_service?: string;
  upnp_st?: string;
  upnp_mx?: number;
  upnp_ttl?: number;
  interface_ip?: string;
  enrich?: boolean;
}

export async function discover(params: DiscoverParams, signal?: AbortSignal): Promise<DiscoverResponse> {
  // Set Axios timeout to the discovery timeout + 15 s buffer so the request
  // doesn't abort before the backend finishes scanning.
  const requestTimeout = ((params.timeout || 5) + 15) * 1000;
  const { data } = await apiClient.get<DiscoverResponse>('/api/discover', {
    params,
    signal,
    timeout: requestTimeout,
  });
  return data;
}
