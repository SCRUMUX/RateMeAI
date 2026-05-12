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
  // Variant B (CMS hub on Railway), as of 1.61.0:
  //   * ``ailookstudio.ru`` and ``www.ailookstudio.ru`` → RU SPA on the
  //     edge VPS.
  //   * Anything else (``ailookstudio.vercel.app`` and Vercel preview
  //     subdomains) → global SPA on Railway.
  // ``ru.ailookstudio.ru`` removed end-to-end in 1.61.0 — no DNS, no
  // cert, no nginx server-block; the ``ru.`` fallback branch is gone.
  if (host === 'ailookstudio.ru' || host === 'www.ailookstudio.ru') return 'ru';
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
