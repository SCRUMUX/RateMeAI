import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

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

export default function AdminLayout({ children }: AdminLayoutProps) {
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
        </div>
      </header>

      <main className="max-w-[1240px] mx-auto px-[var(--space-16)] tablet:px-[var(--space-32)] desktop:px-[var(--space-48)] py-[var(--space-32)] desktop:py-[var(--space-40)]">
        {children}
      </main>
    </div>
  );
}
