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
          <img src="/img/logo.png" alt="AI Look Studio" className="w-9 h-9 rounded-lg object-contain" />
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

          {session && (
            <div className="flex items-center gap-[var(--space-8)]">
              <div className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
                <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
                <span>{balance}</span>
              </div>
              {prov && (
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => setShowLogout(prev => !prev)}
                    className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-10)] py-[var(--space-6)] text-[13px] leading-[18px] font-medium text-[var(--color-text-secondary)] rounded-[var(--radius-12)] cursor-pointer hover:text-[#E6EEF8] transition-colors"
                  >
                    <span className="text-[13px] leading-none">{prov.icon}</span>
                    <span>{prov.name}</span>
                  </button>
                  {showLogout && (
                    <div className="absolute top-full right-0 mt-2 glass-card rounded-[var(--radius-12)] shadow-lg overflow-hidden z-50 min-w-[140px]">
                      <button
                        onClick={() => { logout(); setShowLogout(false); }}
                        className="w-full px-4 py-2.5 text-left text-[13px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] hover:bg-white/5 transition-colors"
                      >
                        Выйти
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
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
