import { useState, useRef, useEffect } from 'react';
import { GlobeIcon, CoinIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';

const PROVIDER_LABELS: Record<string, { icon: string; name: string }> = {
  yandex: { icon: 'Я', name: 'Яндекс' },
  vk_id: { icon: 'VK', name: 'ВКонтакте' },
  web: { icon: '🌐', name: 'Web' },
};

export default function NavBar() {
  const { session, balance, logout } = useApp();
  const [showLogout, setShowLogout] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showLogout) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowLogout(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showLogout]);

  const prov = session?.provider ? PROVIDER_LABELS[session.provider] : null;

  return (
    <nav className="fixed top-0 left-0 right-0 z-[100] glass-nav">
      <div className="max-w-[1200px] mx-auto flex items-center justify-between h-[60px] px-[var(--space-24)]">
        {/* Logo */}
        <div className="flex items-center gap-[var(--space-8)] px-[var(--space-8)] py-[var(--space-4)]">
          <img src="/img/logo.png" alt="AI Look Studio" className="w-11 h-11 rounded-xl object-contain" style={{ mixBlendMode: 'lighten' }} />
          <span className="text-[22px] leading-[30px] font-bold whitespace-nowrap tracking-tight">
            <span className="text-[var(--color-brand-primary)]">AI</span>
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
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setShowLogout(prev => !prev)}
                  className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] border border-[rgba(255,255,255,0.15)] hover:border-[rgba(255,255,255,0.3)] bg-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.08)] transition-all cursor-pointer"
                >
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="8" stroke="currentColor" strokeWidth="1.2"/><circle cx="9" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.2"/><path d="M4.5 15.5c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                  <span>{prov?.name || 'Профиль'}</span>
                </button>
                {showLogout && (
                  <div className="absolute top-full right-0 mt-2 glass-card rounded-[var(--radius-12)] shadow-lg overflow-hidden z-50 min-w-[160px]">
                    <button
                      onClick={() => { logout(); setShowLogout(false); }}
                      className="w-full px-4 py-2.5 text-left text-[14px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] hover:bg-white/5 transition-colors flex items-center gap-2"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 14H3.333A1.333 1.333 0 012 12.667V3.333A1.333 1.333 0 013.333 2H6M10.667 11.333L14 8m0 0l-3.333-3.333M14 8H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      Выйти
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <a href="#app"
              className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] border border-[rgba(255,255,255,0.15)]"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.2"/><path d="M3.5 14c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
              Войти
            </a>
          )}

          <button className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
            <GlobeIcon size={20} className="text-[var(--color-text-muted)]" />
            Русский
          </button>

          <a href="#app"
            className="glass-btn-primary flex items-center px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] rounded-[var(--radius-12)]"
          >
            Попробовать
          </a>
        </div>
      </div>
    </nav>
  );
}
