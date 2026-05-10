import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

import {
  AdminTargetProvider,
  useAdminTarget,
} from '../../lib/admin-target-context';
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
 * Variant B replacement for the old multi-target dropdown — admin
 * always lives on the single primary backend (Railway). We render a
 * compact read-only badge instead of a switcher so the operator
 * still sees which API base their session is bound to (useful when
 * previewing a non-prod build with VITE_API_BASE_URL overridden).
 */
function PrimaryTargetBadge() {
  const { current } = useAdminTarget();
  return (
    <div
      className="flex items-center gap-[var(--space-8)] px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-pill)] border border-blue-400/40 bg-blue-500/15 text-blue-100 text-[12px] leading-[16px] font-medium"
      title={current.apiBase || 'API base пуст'}
    >
      <span className="text-[10px] uppercase tracking-[0.16em] opacity-70">
        Backend
      </span>
      <span>{current.shortLabel}</span>
    </div>
  );
}

/**
 * 1.55.4 — diagnostic gate that runs after the token check.
 *
 * Even with a valid session token, the backend ``require_admin`` may
 * still 403 (user UUID not in ``ADMIN_USER_IDS``, identity email not
 * in ``ADMIN_EMAILS``, or both whitelists empty). The new
 * ``/api/v1/admin/_whoami`` endpoint is auth-required but NOT
 * admin-gated, so we can render an actionable explanation: "your
 * email is X but the whitelist on this server has 0 entries — ask
 * ops to set ADMIN_EMAILS in Railway" or similar.
 */
function AdminGateDiagnostics({ children }: { children: ReactNode }) {
  const { current } = useAdminTarget();
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
  }, []);

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
            <span className="text-amber-100/70">Whitelist:</span>{' '}
            ADMIN_USER_IDS = {info.whitelist_size.user_ids}, ADMIN_EMAILS ={' '}
            {info.whitelist_size.emails}
          </li>
        </ul>
        <p className="text-[13px] leading-[20px] text-amber-100/85 mb-[var(--space-12)]">
          {whitelistEmpty
            ? 'Оба whitelist-а пустые. Это значит, что переменные '
              + 'ADMIN_USER_IDS / ADMIN_EMAILS не загружены в контейнер app — '
              + 'нужно запустить деплой ещё раз (CI синкит ADMIN_EMAILS '
              + 'из секрета) или вручную добавить и перезапустить app.'
            : userHasNoEmail
              ? 'Whitelist непустой, но у текущего OAuth-провайдера нет email-а '
                + '(Yandex без login:email scope, VK ID, либо вход по телефону). '
                + 'Войдите через провайдера, который отдаёт email (Google).'
              : 'Whitelist непустой, но ни один из ваших email-ов в нём не значится. '
                + 'Добавьте нужный адрес в GitHub-секрет ADMIN_EMAILS '
                + '(value: comma-separated) и передеплойте.'}
        </p>
        <p className="text-[12px] leading-[18px] text-amber-100/60">
          Цель: {current.label}
          {info.git ? ` · git=${info.git}` : ''}
        </p>
      </div>
    );
  }

  return <div>{children}</div>;
}

/**
 * Block admin pages when the operator hasn't logged in yet — every
 * admin endpoint would otherwise return 401 and the page would just
 * look broken.
 */
function NoTokenGate({ children }: { children: ReactNode }) {
  const { current, hasToken } = useAdminTarget();
  if (hasToken) {
    return <AdminGateDiagnostics>{children}</AdminGateDiagnostics>;
  }
  return (
    <div className="rounded-[14px] border border-amber-400/30 bg-amber-500/5 px-[var(--space-24)] py-[var(--space-24)] text-amber-100 max-w-[760px]">
      <h2 className="text-[16px] leading-[22px] font-semibold mb-[var(--space-8)]">
        Нужен вход для доступа в админку
      </h2>
      <p className="text-[13px] leading-[20px] text-amber-100/85 mb-[var(--space-12)]">
        Войдите в основной кабинет (OAuth) на этом домене и вернитесь сюда —
        токен подтянется автоматически.
      </p>
      <p className="text-[12px] leading-[18px] text-amber-100/60">
        Backend: {current.label}
      </p>
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
            <PrimaryTargetBadge />
          </div>
        </div>
      </header>

      <main className="max-w-[1240px] mx-auto px-[var(--space-16)] tablet:px-[var(--space-32)] desktop:px-[var(--space-48)] py-[var(--space-32)] desktop:py-[var(--space-40)]">
        <NoTokenGate>{children}</NoTokenGate>
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
