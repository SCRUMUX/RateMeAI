import { GlobeIcon, CoinIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';

interface Props {
  onLoginClick?: () => void;
}

export default function NavBar({ onLoginClick }: Props) {
  const { session, balance, logout } = useApp();

  return (
    <nav className="fixed top-0 left-0 right-0 z-[100] glass-nav">
      <div className="max-w-[1200px] mx-auto flex items-center justify-between h-[60px] px-[var(--space-24)]">
        {/* Logo */}
        <div className="flex items-center gap-[var(--space-8)] px-[var(--space-8)] py-[var(--space-4)]">
          <div className="relative w-11 h-11 shrink-0">
            <div className="absolute inset-0 rounded-xl" style={{ background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.18)' }} />
            <img src="/img/logo.png" alt="AI Look Studio" className="relative w-full h-full rounded-xl object-contain" style={{ mixBlendMode: 'lighten' }} />
          </div>
          <span className="text-[22px] leading-[30px] font-bold whitespace-nowrap tracking-tight">
            <span className="text-[#E6EEF8]">AI</span>
            <span className="text-[var(--color-text-primary)]"> Look Studio</span>
          </span>
        </div>

        {/* Nav links */}
        <div className="flex items-center gap-[var(--space-12)]">
          {['Стили', 'Тарифы', 'API'].map((label) => (
            <a key={label} href={`#${label.toLowerCase()}`}
              className="px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors cursor-pointer"
            >
              {label}
            </a>
          ))}

          {session ? (
            <div className="flex items-center gap-[var(--space-8)]">
              <div className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
                <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
                <span>{balance}</span>
              </div>
              <button
                onClick={logout}
                className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] border border-[rgba(255,255,255,0.15)] hover:border-[rgba(255,255,255,0.3)] bg-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.08)] transition-all cursor-pointer"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-[var(--color-brand-primary)]"><path d="M6 14H3.333A1.333 1.333 0 012 12.667V3.333A1.333 1.333 0 013.333 2H6M10.667 11.333L14 8m0 0l-3.333-3.333M14 8H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Выйти
              </button>
            </div>
          ) : (
            <button
              onClick={onLoginClick}
              className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] border border-[rgba(255,255,255,0.15)] cursor-pointer"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-[var(--color-brand-primary)]"><path d="M10 2h2.667A1.333 1.333 0 0114 3.333v9.334A1.333 1.333 0 0112.667 14H10M6.667 11.333L10 8m0 0L6.667 4.667M10 8H2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              Войти
            </button>
          )}

          <button className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
            <GlobeIcon size={20} className="text-[var(--color-text-muted)]" />
            Русский
          </button>

          {!session && (
            <a href="#app"
              className="glass-btn-primary flex items-center px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] rounded-[var(--radius-12)]"
            >
              Попробовать
            </a>
          )}
        </div>
      </div>
    </nav>
  );
}
