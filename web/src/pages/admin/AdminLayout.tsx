import { useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

import {
  AdminTargetProvider,
  useAdminTarget,
} from '../../lib/admin-target-context';
import type { AdminTargetId } from '../../lib/admin-targets';

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
 * If the operator switches to a target where they aren't logged in
 * (no per-target token), block the page content and explain how to
 * fix it. Without this, every admin endpoint would return 401 and
 * the page would just look broken.
 */
function NoTokenForTargetGate({ children }: { children: ReactNode }) {
  const { current, hasToken, setTarget, targets, switchEpoch } = useAdminTarget();
  // Force a remount of the page content whenever the operator picks
  // a new target so we don't display stale RU data after switching to
  // primary (or vice-versa). Cheap and bullet-proof; the alternative
  // is threading switchEpoch into every page's effect dependencies.
  if (hasToken) {
    return (
      <div key={`${current.id}:${switchEpoch}`}>{children}</div>
    );
  }

  const otherWithToken = targets.find(
    (t) => t.id !== current.id && Boolean(localStorage.getItem(`ailook_session_token__${t.id}`)),
  );

  return (
    <div className="rounded-[14px] border border-amber-400/30 bg-amber-500/5 px-[var(--space-24)] py-[var(--space-24)] text-amber-100 max-w-[760px]">
      <h2 className="text-[16px] leading-[22px] font-semibold mb-[var(--space-8)]">
        Нужен вход на target «{current.label}»
      </h2>
      <p className="text-[13px] leading-[20px] text-amber-100/85 mb-[var(--space-16)]">
        У этого инстанса своя база сессий. Чтобы дёргать админ-эндпоинты,
        войдите в основной кабинет на нужном домене и вернитесь сюда.
      </p>
      <ul className="text-[12px] leading-[18px] text-amber-100/70 space-y-[var(--space-4)] mb-[var(--space-16)] list-disc pl-[var(--space-20)]">
        <li>
          Для primary: войти на{' '}
          <a
            href="https://ailookstudio.ru/auth"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-white"
          >
            ailookstudio.ru/auth
          </a>{' '}
          и потом открыть{' '}
          <code className="bg-black/30 px-[4px] py-[1px] rounded">
            /admin/users
          </code>
          .
        </li>
        <li>
          Для RU: войти на{' '}
          <a
            href="https://ru.ailookstudio.ru/auth"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-white"
          >
            ru.ailookstudio.ru/auth
          </a>{' '}
          и потом открыть тот же путь админки.
        </li>
      </ul>
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
