export type MarketAuthProvider = 'google' | 'yandex' | 'vk-id';

export interface MarketConfig {
  id: string;
  authProviders: MarketAuthProvider[];
  authDescription: string;
}

const MARKET_CONFIGS: Record<string, MarketConfig> = {
  global: {
    id: 'global',
    authProviders: ['google'],
    authDescription: 'Sign in with Google to access the app and payments',
  },
  ru: {
    id: 'ru',
    authProviders: ['yandex', 'vk-id'],
    authDescription: 'Войдите через Яндекс или ВКонтакте, чтобы открыть приложение и оплату',
  },
};

function normalizeMarketId(raw: string | null | undefined): string | null {
  const value = (raw ?? '').trim().toLowerCase();
  return value || null;
}

function detectMarketFromHostname(): string {
  if (typeof window === 'undefined') return 'global';
  const host = window.location.hostname.toLowerCase();
  if (host.startsWith('ru.')) return 'ru';
  return 'global';
}

export function getCurrentMarketId(): string {
  const envValue = normalizeMarketId(import.meta.env.VITE_MARKET_ID);
  return envValue ?? detectMarketFromHostname();
}

export function getCurrentMarketConfig(): MarketConfig {
  const marketId = getCurrentMarketId();
  return MARKET_CONFIGS[marketId] ?? MARKET_CONFIGS.global;
}
