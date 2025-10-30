import { z } from 'zod';

export const pageSizes = [12, 24, 48] as const;

export const SettingsSchema = z.object({
  protocol: z.union([z.literal('all'), z.literal('upnp'), z.literal('mdns'), z.literal('wsd')]).default('all'),
  timeoutVal: z.number().int().min(1).max(300).default(5),
  mdnsService: z.string().default('_services._dns-sd._udp.local.'),
  upnpST: z.string().default('ssdp:all'),
  upnpMX: z.number().int().min(1).max(5).default(3),
  upnpTTL: z.number().int().min(1).max(16).default(2),
  interfaceIp: z.string().optional().default(''),
  showRaw: z.boolean().default(false),
  activeTab: z.union([z.literal('all'), z.literal('upnp'), z.literal('mdns'), z.literal('wsd')]).default('all'),
  pageSize: z.union([z.literal(12), z.literal(24), z.literal(48)]).default(12),
});

export type UISettings = z.infer<typeof SettingsSchema>;

const STORAGE_KEY = 'firefly_settings';

export function loadSettings(): UISettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return SettingsSchema.parse({});
    const parsed = JSON.parse(raw);
    return SettingsSchema.parse(parsed);
  } catch {
    return SettingsSchema.parse({});
  }
}

export function saveSettings(partial: Partial<UISettings>): void {
  const current = loadSettings();
  const next = { ...current, ...partial };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}
