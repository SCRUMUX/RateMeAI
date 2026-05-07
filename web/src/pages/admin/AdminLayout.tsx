import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

import {
  AdminTargetProvider,
  useAdminTarget,
} from '../../lib/admin-target-context';
import { tokenStorageKey, type AdminTargetId } from '../../lib/admin-targets';
import { adminWhoami, ApiError, type AdminWhoamiResponse } from '../../lib/api';

interface AdminLayoutProps {
  children: ReactNode;
}

interface AdminTab {
  to: string;
  label: string;
  match: (pathname: string) => boolean;
}

const TABS: AdminTab[] = [
  {
    to: '/admin/users',
    label: 'Пользователи',
    match: (p) => p.startsWith('/admin/users'),
  },
  {
    to: '/admin/landing',
    label: 'Landing CMS',
    match: (p) => p.startsWith('/admin/landing'),
  },
  {
    to: '/admin/styles',
    label: 'Каталог стилей',
    match: (p) => p === '/admin/styles' || p.startsWith('/admin/styles/'),
  },
  {
    to: '/admin/conflicts',
    label: 'Конфликты названий',
    match: (p) => p.startsWith('/admin/conflicts'),
  },
];

/**
 * Header dropdown that lets the operator switch between primary and
 * RU edge instances. Each target has its OWN session token in
 * localStorage (see ``admin-targets.ts``); the dropdown surfaces
 * which targets currently have a token so it's obvious whether the
 * next click will work or pop a login prompt.
 */
function TargetSwitcher() {
  const { current, targets, setTarget } = useAdminTarget();
  const [open, setOpen] = useState(false);

  const accent =
    current.id === 'ru'
      ? 'bg-emerald-500/15 border-emerald-400/40 text-emerald-100'
      : 'bg-blue-500/15 border-blue-400/40 text-blue-100';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-[var(--space-8)] px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-pill)] border text-[12px] leading-[16px] font-medium transition-colors ${accent}`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="text-[10px] uppercase tracking-[0.16em] opacity-70">
          Цель
        </span>
        <span>{current.shortLabel}</span>
        <span className="text-[10px] opacity-60">▾</span>
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute right-0 mt-[var(--space-8)] min-w-[260px] rounded-[12px] border border-white/10 bg-[#13191F] shadow-2xl z-40 overflow-hidden"
          onMouseLeave={() => setOpen(false)}
        >
          {targets.map((t) => {
            const active = t.id === current.id;
            return (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => {
                    setTarget(t.id as AdminTargetId);
                    setOpen(false);
                  }}
                  className={`w-full text-left px-[var(--space-16)] py-[var(--space-12)] text-[13px] leading-[18px] flex flex-col gap-[2px] transition-colors ${
                    active
                      ? 'bg-white/5 text-white'
                      : 'text-[#cbd5e0] hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <span className="font-medium">{t.label}</span>
                  <span className="text-[11px] text-[#8b95a3] truncate">
                    {t.apiBase || '— API base пуст —'}
                  </span>
                </button>
              </li>
            );
          })}
          <li className="px-[var(--space-16)] py-[var(--space-8)] border-t border-white/10 text-[11px] leading-[15px] text-[#8b95a3]">
            Юзеры, кредиты и блокировки относятся только к выбранному
            серверу. Контент (стили / лендинг) можно записать сразу на
            оба через кнопку «Применить на оба».
          </li>
        </ul>
      )}
    </div>
  );
}

/**
 * 1.55.4 — diagnostic gate that runs AFTER ``NoTokenForTargetGate``.
 *
 * Even with a valid session token, the backend ``require_admin`` may
 * still 403 (user UUID not in ``ADMIN_USER_IDS``, identity email not
 * in ``ADMIN_EMAILS``, or both whitelists empty on this region).
 * Pre-1.55.4 every page just showed "Доступ запрещён" without saying
 * why, which led to hours of debugging "is the env var set? does my
 * email match? am I on the right region?".
 *
 * The new ``GET /api/v1/admin/_whoami`` endpoint is auth-required but
 * NOT admin-gated, so we can call it with the same token the user
 * already has and render an actionable explanation: "your email is
 * X but the whitelist on this server has 0 entries — ask ops to set
 * ADMIN_EMAILS in .env.ru" or similar.
 */
function AdminGateDiagnostics({ children }: { children: ReactNode }) {
  const { current, switchEpoch } = useAdminTarget();
  const [info, setInfo] = useState<AdminWhoamiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setInfo(null);
    adminWhoami()
      .then((res) => {
        if (cancelled) return;
        setInfo(res);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) {
          setError(
            'Токен не принят сервером. Возможно, сессия истекла — '
              + 'выйдите из кабинета и войдите снова.',
          );
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError('Не удалось выполнить диагностику админки.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [current.id, switchEpoch]);

  if (loading) {
    return (
      <div className="text-[13px] text-[#8b95a3] py-[var(--space-32)] text-center">
        Проверка прав на сервере «{current.shortLabel}»…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-[14px] border border-red-500/30 bg-red-500/[0.06] px-[var(--space-24)] py-[var(--space-24)] text-red-100 max-w-[760px]">
        <h2 className="text-[16px] leading-[22px] font-semibold mb-[var(--space-8)]">
          Не удалось проверить права на «{current.label}»
        </h2>
        <p className="text-[13px] leading-[20px] text-red-100/85">{error}</p>
      </div>
    );
  }

  if (info && !info.is_admin) {
    const whitelistEmpty =
      info.whitelist_size.user_ids === 0 && info.whitelist_size.emails === 0;
    const userHasNoEmail = info.identity_emails.length === 0;
    return (
      <div className="rounded-[14px] border border-amber-400/30 bg-amber-500/[0.06] px-[var(--space-24)] py-[var(--space-24)] text-amber-100 max-w-[840px]">
        <h2 className="text-[16px] leading-[22px] font-semibold mb-[var(--space-12)]">
          Этот аккаунт не админ на «{info.deployment_mode}» (
          {info.market_id || current.shortLabel})
        </h2>
        <ul className="text-[13px] leading-[20px] text-amber-100/90 space-y-[var(--space-6)] mb-[var(--space-12)]">
          <li>
            <span className="text-amber-100/70">user_id:</span>{' '}
            <code className="font-mono text-[12px]">{info.user_id}</code>
          </li>
          <li>
            <span className="text-amber-100/70">Привязанные emails:</span>{' '}
            {userHasNoEmail
              ? '— (Yandex/VK без login:email scope или phone-логин)'
              : info.identity_emails.join(', ')}
          </li>
          <li>
            <span className="text-amber-100/70">Whitelist на этом сервере:</span>{' '}
            ADMIN_USER_IDS = {info.whitelist_size.user_ids}, ADMIN_EMAILS ={' '}
            {info.whitelist_size.emails}
          </li>
        </ul>
        <p className="text-[13px] leading-[20px] text-amber-100/85 mb-[var(--space-12)]">
          {whitelistEmpty
            ? 'На этом сервере оба whitelist-а пустые. Это значит, что переменные '
              + 'ADMIN_USER_IDS / ADMIN_EMAILS не загружены в контейнер app — '
              + 'нужно запустить деплой ещё раз (CI 1.55.4+ синкит ADMIN_EMAILS '
              + 'в .env.ru через secrets.ADMIN_EMAILS) или вручную добавить '
              + 'строку и перезапустить app.'
            : userHasNoEmail
              ? 'Whitelist непустой, но у текущего OAuth-провайдера нет email-а '
                + '(Yandex без login:email scope, VK ID, либо вход по телефону). '
                + 'Войдите через провайдера, который отдаёт email (Google).'
              : 'Whitelist непустой, но ни один из ваших email-ов в нём не значится. '
                + 'Добавьте нужный адрес в GitHub-секрет ADMIN_EMAILS '
                + '(value: comma-separated) и передеплойте — CI запишет новый '
                + 'whitelist одновременно на Railway и в .env.ru на RU-edge.'}
        </p>
        <p className="text-[12px] leading-[18px] text-amber-100/60">
          Цель: {current.label}
          {info.git ? ` · git=${info.git}` : ''}
        </p>
      </div>
    );
  }

  return (
    <div key={`${current.id}:${switchEpoch}`}>{children}</div>
  );
}

/**
 * If the operator switches to a target where they aren't logged in
 * (no per-target token), block the page content and explain how to
 * fix it. Without this, every admin endpoint would return 401 and
 * the page would just look broken.
 */
function NoTokenForTargetGate({ children }: { children: ReactNode }) {
  const { current, hasToken, setTarget, targets } = useAdminTarget();
  if (hasToken) {
    return <AdminGateDiagnostics>{children}</AdminGateDiagnostics>;
  }

  const otherWithToken = targets.find(
    (t) => t.id !== current.id
      && Boolean(localStorage.getItem(tokenStorageKey(t.id))),
  );

  // Cross-origin reality check (1.55.1): localStorage is per-origin,
  // so a session token written on ru.ailookstudio.ru is *literally
  // invisible* to scripts running on ailookstudio.ru. Switching to RU
  // from a non-RU origin will never find the token even after a
  // separate-tab login. We detect it from window.location.host vs
  // the target's apiBase host and show a direct "open RU admin"
  // shortcut instead of a useless login prompt.
  const targetHost = (() => {
    try { return new URL(current.apiBase).host; } catch { return ''; }
  })();
  const currentHost = typeof window !== 'undefined' ? window.location.host : '';
  const isCrossOrigin =
    targetHost !== '' && currentHost !== '' && targetHost !== currentHost;
  const targetAdminUrl =
    isCrossOrigin && current.apiBase
      ? `${current.apiBase.replace(/\/+$/, '')}/admin/users`
      : null;

  return (
    <div className="rounded-[14px] border border-amber-400/30 bg-amber-500/5 px-[var(--space-24)] py-[var(--space-24)] text-amber-100 max-w-[760px]">
      <h2 className="text-[16px] leading-[22px] font-semibold mb-[var(--space-8)]">
        Нужен вход на target «{current.label}»
      </h2>
      {isCrossOrigin ? (
        <>
          <p className="text-[13px] leading-[20px] text-amber-100/85 mb-[var(--space-12)]">
            Админка target «{current.shortLabel}» живёт на другом домене
            ({targetHost}), и его сессия хранится только там — из этой
            вкладки её не достать. Откройте админку напрямую на нужном
            домене:
          </p>
          {targetAdminUrl && (
            <a
              href={targetAdminUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-[var(--space-8)] px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-emerald-600 hover:bg-emerald-500 text-white text-[13px] leading-[18px] font-medium mb-[var(--space-16)]"
            >
              Открыть админку «{current.shortLabel}» в новой вкладке →
            </a>
          )}
        </>
      ) : (
        <p className="text-[13px] leading-[20px] text-amber-100/85 mb-[var(--space-16)]">
          У этого инстанса своя база сессий. Войдите в основной кабинет
          на этом домене и вернитесь сюда — токен подтянется автоматически.
        </p>
      )}
      {otherWithToken && (
        <button
          type="button"
          onClick={() => setTarget(otherWithToken.id)}
          className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-white/10 hover:bg-white/15 text-white text-[13px] leading-[18px] font-medium"
        >
          Переключиться обратно на {otherWithToken.shortLabel}
        </button>
      )}
    </div>
  );
}

function AdminLayoutInner({ children }: AdminLayoutProps) {
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen bg-[#0E1216] text-[#E6EEF8]">
      <header className="border-b border-white/10 bg-[#0E1216]/80 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-[1240px] mx-auto px-[var(--space-16)] tablet:px-[var(--space-32)] desktop:px-[var(--space-48)] py-[var(--space-16)] flex flex-col tablet:flex-row tablet:items-end tablet:justify-between gap-[var(--space-12)] tablet:gap-[var(--space-24)]">
          <div className="flex flex-col gap-[var(--space-4)]">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[#5a6470]">
              RateMeAI Admin
            </span>
            <h1 className="text-[20px] tablet:text-[22px] leading-[28px] font-semibold text-white">
              Панель администратора
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-[var(--space-12)] tablet:gap-[var(--space-16)]">
            <nav className="flex flex-wrap gap-[var(--space-4)]" aria-label="Admin sections">
              {TABS.map((tab) => {
                const active = tab.match(pathname);
                return (
                  <Link
                    key={tab.to}
                    to={tab.to}
                    className={`px-[var(--space-16)] py-[var(--space-8)] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium border transition-colors ${
                      active
                        ? 'bg-blue-500/15 border-blue-400/40 text-white'
                        : 'border-white/10 text-[#8b95a3] hover:text-white hover:bg-white/5'
                    }`}
                  >
                    {tab.label}
                  </Link>
                );
              })}
            </nav>
            <TargetSwitcher />
          </div>
        </div>
      </header>

      <main className="max-w-[1240px] mx-auto px-[var(--space-16)] tablet:px-[var(--space-32)] desktop:px-[var(--space-48)] py-[var(--space-32)] desktop:py-[var(--space-40)]">
        <NoTokenForTargetGate>{children}</NoTokenForTargetGate>
      </main>
    </div>
  );
}

export default function AdminLayout({ children }: AdminLayoutProps) {
  return (
    <AdminTargetProvider>
      <AdminLayoutInner>{children}</AdminLayoutInner>
    </AdminTargetProvider>
  );
}
