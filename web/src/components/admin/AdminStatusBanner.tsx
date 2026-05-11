/**
 * Two-region admin status banner.
 *
 * The project runs two independent admin surfaces — one per region —
 * because RU PII must not cross to the Global Railway backend and
 * vice versa (152-ФЗ). That means an admin who logged in on one
 * region's domain is NOT logged in on the other; the same Google
 * account just buys two separate Bearer tokens, one per origin.
 *
 * Without this banner that's deeply confusing: open
 * ``ailookstudio.ru/admin``, you're authed. Open
 * ``ailookstudio.vercel.app/admin`` in another tab, you get a 401 and
 * it looks like a bug. This banner makes the boundary explicit:
 *
 *   * For THIS server (the one currently serving the SPA) we call
 *     ``GET /api/v1/admin/_whoami`` (auth-required, NOT admin-gated)
 *     and render: signed-in email + admin status + market_id + git SHA.
 *
 *   * For the PAIR server we cannot probe directly (CORS / CSP), so
 *     we render its public URL with a button that opens
 *     ``/admin/_whoami`` in a new tab. The operator visually confirms
 *     they're authed on both — or signs in on the one that's missing.
 *
 * The pair-server URL is hard-wired so the banner works even when the
 * other origin is unreachable from the browser: the operator just
 * sees the button and knows where to click.
 */

import { useEffect, useMemo, useState } from 'react';

import { adminWhoami, ApiError, type AdminWhoamiResponse } from '../../lib/api';

const PAIR_URL_BY_MARKET: Record<string, { url: string; label: string }> = {
  ru: {
    url: 'https://ailookstudio.vercel.app/admin/landing',
    label: 'Global (ailookstudio.vercel.app)',
  },
  global: {
    url: 'https://ailookstudio.ru/admin/landing',
    label: 'RU (ailookstudio.ru)',
  },
};

const FALLBACK_PAIR = {
  url: 'https://ailookstudio.ru/admin/landing',
  label: 'RU (ailookstudio.ru)',
};

type LoadState =
  | { kind: 'loading' }
  | { kind: 'no-token' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; info: AdminWhoamiResponse };

function describeMarket(marketId: string | undefined): string {
  const m = (marketId || '').toLowerCase();
  if (m === 'ru') return 'RU edge (ailookstudio.ru)';
  if (m === 'global') return 'Global (ailookstudio.vercel.app)';
  return marketId || 'unknown';
}

function pickPair(marketId: string | undefined): { url: string; label: string } {
  const m = (marketId || '').toLowerCase();
  return PAIR_URL_BY_MARKET[m] ?? FALLBACK_PAIR;
}

export function AdminStatusBanner() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });
    adminWhoami()
      .then((info) => {
        if (cancelled) return;
        setState({ kind: 'loaded', info });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          setState({ kind: 'no-token' });
        } else if (err instanceof Error) {
          setState({ kind: 'error', message: err.message });
        } else {
          setState({ kind: 'error', message: 'Не удалось получить статус админки' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Pair host is derived from whatever the server tells us about its
  // own market. Falls back to RU before we have data because the
  // RU edge is the most common "other side" for Railway admins.
  const pair = useMemo(() => {
    if (state.kind === 'loaded') return pickPair(state.info.market_id);
    return FALLBACK_PAIR;
  }, [state]);

  return (
    <div className="rounded-[16px] border border-white/10 bg-white/[0.03] px-[var(--space-20)] py-[var(--space-16)] mb-[var(--space-24)]">
      <div className="grid grid-cols-1 tablet:grid-cols-2 gap-[var(--space-20)]">
        {/* THIS server */}
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.18em] text-[#5a6470] mb-[var(--space-8)]">
            Этот сервер
          </h3>
          <CurrentServerCell state={state} />
        </div>

        {/* PAIR server */}
        <div className="border-t tablet:border-t-0 tablet:border-l border-white/10 tablet:pl-[var(--space-20)] pt-[var(--space-16)] tablet:pt-0">
          <h3 className="text-[11px] uppercase tracking-[0.18em] text-[#5a6470] mb-[var(--space-8)]">
            Парный сервер
          </h3>
          <PairServerCell pair={pair} />
        </div>
      </div>
    </div>
  );
}

function CurrentServerCell({ state }: { state: LoadState }) {
  if (state.kind === 'loading') {
    return (
      <p className="text-[13px] text-[#8b95a3]">Проверяю /admin/_whoami…</p>
    );
  }

  if (state.kind === 'no-token') {
    return (
      <div>
        <p className="text-[13px] text-amber-100 mb-[var(--space-4)]">
          Не залогинен на этом домене.
        </p>
        <p className="text-[12px] text-[#8b95a3]">
          Войдите через OAuth на этом домене (Google рекомендован для
          админов): администратор и публичный логин используют один и
          тот же session-токен.
        </p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <p className="text-[13px] text-red-200">
        Ошибка: <span className="opacity-80">{state.message}</span>
      </p>
    );
  }

  const { info } = state;
  const status = info.is_admin ? 'Админ' : 'Залогинен, но не админ';
  const statusColor = info.is_admin ? 'text-emerald-300' : 'text-amber-200';
  const emails = info.identity_emails.length
    ? info.identity_emails.join(', ')
    : '— (вход не через email-провайдер)';
  return (
    <div className="text-[13px] leading-[20px] space-y-[var(--space-4)]">
      <p className={`font-semibold ${statusColor}`}>{status}</p>
      <p>
        <span className="text-[#5a6470] mr-[var(--space-6)]">market:</span>
        {describeMarket(info.market_id)}
        {info.deployment_mode ? ` · ${info.deployment_mode}` : ''}
      </p>
      <p>
        <span className="text-[#5a6470] mr-[var(--space-6)]">emails:</span>
        <span className="font-mono text-[12px] break-all">{emails}</span>
      </p>
      <p className="text-[11px] text-[#5a6470]">
        whitelist size — ADMIN_USER_IDS={info.whitelist_size.user_ids},
        ADMIN_EMAILS={info.whitelist_size.emails}
        {info.git ? ` · git=${info.git}` : ''}
      </p>
    </div>
  );
}

function PairServerCell({ pair }: { pair: { url: string; label: string } }) {
  return (
    <div className="text-[13px] leading-[20px]">
      <p className="text-[#c5cdd9] mb-[var(--space-6)]">{pair.label}</p>
      <p className="text-[12px] text-[#8b95a3] mb-[var(--space-12)]">
        Браузер не может проверить статус другого домена напрямую
        (Same-Origin Policy). Откройте парную админку в новой вкладке
        и убедитесь, что там тоже залогинены. На каждой стороне нужен
        отдельный вход — это не баг, это разделение PII по 152-ФЗ.
      </p>
      <a
        href={pair.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-[var(--space-6)] px-[var(--space-14)] py-[var(--space-8)] rounded-[var(--radius-pill)] border border-blue-400/40 bg-blue-500/15 text-blue-100 text-[12px] leading-[16px] font-medium hover:bg-blue-500/25"
      >
        Открыть парную админку
        <span aria-hidden="true">→</span>
      </a>
    </div>
  );
}
