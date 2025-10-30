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
}

export async function discover(params: DiscoverParams, signal?: AbortSignal): Promise<DiscoverResponse> {
  const { data } = await apiClient.get<DiscoverResponse>('/api/discover', { params, signal });
  return data;
}
