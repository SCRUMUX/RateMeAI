import { AicaIcon, GlobeIcon, CoinIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';

export default function NavBar() {
  const { session, balance } = useApp();

  return (
    <nav className="fixed top-0 left-0 right-0 z-[100] glass-nav">
      <div className="max-w-[1200px] mx-auto flex items-center justify-between h-[60px] px-[var(--space-24)]">
        {/* Logo */}
        <div className="flex items-center gap-[var(--space-6)] px-[var(--space-8)] py-[var(--space-4)]">
          <AicaIcon size={24} className="text-[var(--color-brand-primary)] -rotate-45" />
          <span className="text-[20px] leading-[28px] font-semibold whitespace-nowrap">
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
            <div className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
              <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
              <span>{balance}</span>
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
