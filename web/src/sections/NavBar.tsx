import { useState, useRef, useEffect } from 'react';
import { GlobeIcon, CoinIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import LinkedAccountsPanel from '../components/LinkedAccountsPanel';

interface Props {
  onLoginClick?: () => void;
}

export default function NavBar({ onLoginClick }: Props) {
  const { session, balance, logout } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

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
            <div className="relative flex items-center gap-[var(--space-8)]" ref={menuRef}>
              <button
                onClick={() => setMenuOpen(v => !v)}
                className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] cursor-pointer"
              >
                <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
                <span>{balance}</span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className={`transition-transform ${menuOpen ? 'rotate-180' : ''}`}>
                  <path d="M3 5L6 8L9 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>

              {menuOpen && (
                <div
                  className="absolute top-full right-0 mt-2 w-[340px] glass-card rounded-[var(--radius-12)] p-[var(--space-20)] flex flex-col gap-[var(--space-16)]"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  <LinkedAccountsPanel />
                  <a
                    href="/link"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-8)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-8)] hover:bg-[rgba(255,255,255,0.06)] transition-all cursor-pointer no-underline"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6.667 8.667a3.333 3.333 0 005.026.36l2-2a3.334 3.334 0 00-4.714-4.714L8.053 3.24" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/><path d="M9.333 7.333a3.333 3.333 0 00-5.026-.36l-2 2a3.334 3.334 0 004.714 4.714l.927-.926" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    Привязать аккаунт
                  </a>
                  <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
                  <button
                    onClick={() => { setMenuOpen(false); logout(); }}
                    className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-8)] text-[14px] leading-[20px] font-medium text-[#FF4D6A] rounded-[var(--radius-8)] hover:bg-[rgba(255,77,106,0.08)] transition-all cursor-pointer"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 14H3.333A1.333 1.333 0 012 12.667V3.333A1.333 1.333 0 013.333 2H6M10.667 11.333L14 8m0 0l-3.333-3.333M14 8H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    Выйти
                  </button>
                </div>
              )}
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
