import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { GlobeIcon, CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import LinkedAccountsPanel from '../components/LinkedAccountsPanel';
import logoSrc from '../assets/logo.png';

interface Props {
  onLoginClick?: () => void;
  onOpenStorage?: () => void;
  onHomeClick?: () => void;
  onCtaClick?: () => void;
  hideNavLinks?: boolean;
  mode?: 'landing' | 'app';
}

export default function NavBar({ onLoginClick, onOpenStorage, onHomeClick, onCtaClick, hideNavLinks, mode = 'landing' }: Props) {
  const { session, balance, logout, taskHistoryCount, canAccessApp } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [mobileMenuOpen]);

  return (
    <>
    <nav className={`${mode === 'app' ? 'relative shrink-0' : 'fixed top-0 left-0 right-0'} z-[100] glass-nav`}>
      <div className="max-w-[1200px] mx-auto flex items-center justify-between h-[52px] tablet:h-[60px] px-[var(--space-16)] tablet:px-[var(--space-24)]">
        {/* Logo */}
        {onHomeClick ? (
          <button onClick={onHomeClick} className="flex items-center gap-[var(--space-8)] px-[var(--space-8)] py-[var(--space-4)] cursor-pointer">
            <div className="relative w-10 h-10 tablet:w-11 tablet:h-11 shrink-0">
              <div className="absolute inset-0 rounded-xl" style={{ background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.18)' }} />
              <img src={logoSrc} alt="AI Look Studio" className="relative w-full h-full rounded-xl object-contain" style={{ mixBlendMode: 'lighten' }} />
            </div>
            <span className="hidden tablet:inline text-[22px] leading-[30px] font-bold whitespace-nowrap tracking-tight">
              <span className="text-[#E6EEF8]">AI</span>
              <span className="text-[var(--color-text-primary)]"> Look Studio</span>
            </span>
          </button>
        ) : (
          <Link to="/" className="flex items-center gap-[var(--space-8)] px-[var(--space-8)] py-[var(--space-4)] no-underline">
            <div className="relative w-10 h-10 tablet:w-11 tablet:h-11 shrink-0">
              <div className="absolute inset-0 rounded-xl" style={{ background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.18)' }} />
              <img src={logoSrc} alt="AI Look Studio" className="relative w-full h-full rounded-xl object-contain" style={{ mixBlendMode: 'lighten' }} />
            </div>
            <span className="hidden tablet:inline text-[22px] leading-[30px] font-bold whitespace-nowrap tracking-tight">
              <span className="text-[#E6EEF8]">AI</span>
              <span className="text-[var(--color-text-primary)]"> Look Studio</span>
            </span>
          </Link>
        )}

        {/* Desktop nav links */}
        <div className="hidden tablet:flex items-center gap-[var(--space-12)]">
          {mode === 'app' ? (
            onHomeClick ? (
              <button
                onClick={onHomeClick}
                className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors cursor-pointer"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                На главную
              </button>
            ) : (
              <Link
                to="/"
                className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors no-underline"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                На главную
              </Link>
            )
          ) : !hideNavLinks && (
            [{label: 'Стили', href: '#стили'}, {label: 'Тарифы', href: '#тарифы'}, {label: 'API', href: '/api/v1/docs', external: true}].map((item) => (
              <a key={item.label} href={item.href}
                {...(item.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                className="px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors cursor-pointer"
              >
                {item.label}
              </a>
            ))
          )}

          {session ? (
            <div className="relative flex items-center gap-[var(--space-6)]" ref={menuRef}>
              {mode === 'app' && onOpenStorage && (
                <button
                  onClick={onOpenStorage}
                  className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-10)] py-[var(--space-6)] text-[13px] leading-[18px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] cursor-pointer"
                >
                  <ImageIcon size={15} className="text-[var(--color-brand-primary)]" />
                  <span>{taskHistoryCount}</span>
                </button>
              )}
              <button
                onClick={() => setMenuOpen(v => !v)}
                className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-10)] py-[var(--space-6)] text-[13px] leading-[18px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] cursor-pointer"
              >
                <CoinIcon size={15} className="text-[var(--color-brand-primary)]" />
                <span>Баланс {balance}</span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className={`transition-transform ${menuOpen ? 'rotate-180' : ''}`}>
                  <path d="M3 5L6 8L9 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>

              {menuOpen && (
                <div
                  className="absolute top-full right-0 mt-2 w-[340px] rounded-[var(--radius-12)] p-[var(--space-20)] flex flex-col gap-[var(--space-16)]"
                  style={{ background: 'rgba(12, 16, 24, 0.95)', border: '1px solid rgba(255,255,255,0.10)', backdropFilter: 'blur(20px)' }}
                >
                  <Link
                    to="/#тарифы"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-8)] text-[14px] leading-[20px] font-medium text-[var(--color-brand-primary)] rounded-[var(--radius-8)] hover:bg-[rgba(255,255,255,0.06)] transition-all cursor-pointer no-underline"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.2"/><path d="M8 5v6M5 8h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                    Пополнить баланс
                  </Link>
                  <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
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

          {mode !== 'app' && (
            onCtaClick ? (
              <button
                onClick={onCtaClick}
                className="glass-btn-primary flex items-center px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] rounded-[var(--radius-12)] cursor-pointer"
              >
                {canAccessApp ? 'Начать' : 'Получить доступ'}
              </button>
            ) : (
              <Link to="/app"
                className="glass-btn-primary flex items-center px-[var(--space-12)] py-[var(--space-6)] text-[14px] leading-[20px] rounded-[var(--radius-12)] no-underline"
              >
                {canAccessApp ? 'Приложение' : 'Открыть приложение'}
              </Link>
            )
          )}
        </div>

        {/* Mobile: storage + balance + burger */}
        <div className="flex tablet:hidden items-center gap-[var(--space-6)]">
          {session && mode === 'app' && onOpenStorage && (
            <button
              onClick={onOpenStorage}
              className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-8)] py-[var(--space-4)] text-[13px] leading-[18px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] cursor-pointer"
            >
              <ImageIcon size={15} className="text-[var(--color-brand-primary)]" />
              <span>{taskHistoryCount}</span>
            </button>
          )}
          {session && (
            <div className="glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-8)] py-[var(--space-4)] text-[13px] leading-[18px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
              <CoinIcon size={15} className="text-[var(--color-brand-primary)]" />
              <span>{balance}</span>
            </div>
          )}
          <button
            onClick={() => setMobileMenuOpen(v => !v)}
            className="glass-btn-ghost flex items-center justify-center w-11 h-11 rounded-[var(--radius-12)] cursor-pointer"
            aria-label="Меню"
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
              {mobileMenuOpen ? (
                <path d="M6 6L18 18M18 6L6 18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              ) : (
                <>
                  <path d="M3 6H21" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                  <path d="M3 12H21" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                  <path d="M3 18H21" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                </>
              )}
            </svg>
          </button>
        </div>
      </div>

    </nav>

    {/* Mobile drawer — rendered outside nav to avoid backdrop-filter containing block */}
    <AnimatePresence>
      {mobileMenuOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="tablet:hidden fixed inset-0 top-[52px] z-[100] flex flex-col gap-[var(--space-8)] p-[var(--space-20)] overflow-y-auto"
          style={{ background: 'rgb(8, 12, 18)' }}
        >
          {/* Navigation links */}
          <div className="flex flex-col gap-[var(--space-4)]">
            {mode === 'app' ? (
              onHomeClick ? (
                <button
                  onClick={() => { setMobileMenuOpen(false); onHomeClick(); }}
                  className="flex items-center gap-[var(--space-8)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors cursor-pointer rounded-[var(--radius-12)] hover:bg-[rgba(255,255,255,0.06)]"
                >
                  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                    <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  На главную
                </button>
              ) : (
                <Link
                  to="/"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center gap-[var(--space-8)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors cursor-pointer rounded-[var(--radius-12)] hover:bg-[rgba(255,255,255,0.06)] no-underline"
                >
                  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                    <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  На главную
                </Link>
              )
            ) : !hideNavLinks ? (
              [{label: 'Стили', href: '#стили'}, {label: 'Тарифы', href: '#тарифы'}, {label: 'API', href: '/api/v1/docs', external: true}].map((item) => (
                <a key={item.label} href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  {...(item.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                  className="px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors cursor-pointer rounded-[var(--radius-12)] hover:bg-[rgba(255,255,255,0.06)]"
                >
                  {item.label}
                </a>
              ))
            ) : null}
          </div>

          <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />

          {session ? (
            <div className="flex flex-col gap-[var(--space-8)]">
              <Link
                to="/#тарифы"
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center gap-[var(--space-10)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[var(--color-brand-primary)] rounded-[var(--radius-12)] hover:bg-[rgba(255,255,255,0.06)] transition-all cursor-pointer no-underline"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.2"/><path d="M8 5v6M5 8h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                Пополнить баланс
              </Link>

              <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />

              <LinkedAccountsPanel />

              <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />

              <a
                href="/link"
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center gap-[var(--space-10)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] hover:bg-[rgba(255,255,255,0.06)] transition-all cursor-pointer no-underline"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><path d="M6.667 8.667a3.333 3.333 0 005.026.36l2-2a3.334 3.334 0 00-4.714-4.714L8.053 3.24" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/><path d="M9.333 7.333a3.333 3.333 0 00-5.026-.36l-2 2a3.334 3.334 0 004.714 4.714l.927-.926" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Привязать аккаунт
              </a>

              <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />

              <button
                onClick={() => { setMobileMenuOpen(false); logout(); }}
                className="flex items-center gap-[var(--space-10)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[#FF4D6A] rounded-[var(--radius-12)] hover:bg-[rgba(255,77,106,0.08)] transition-all cursor-pointer"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><path d="M6 14H3.333A1.333 1.333 0 012 12.667V3.333A1.333 1.333 0 013.333 2H6M10.667 11.333L14 8m0 0l-3.333-3.333M14 8H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Выйти
              </button>

              {mode !== 'app' && (
                onCtaClick ? (
                  <button
                    onClick={() => { setMobileMenuOpen(false); onCtaClick(); }}
                    className="glass-btn-primary flex items-center justify-center px-[var(--space-16)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)] text-center cursor-pointer"
                  >
                    {canAccessApp ? 'Начать' : 'Получить доступ'}
                  </button>
                ) : (
                  <Link
                    to="/app"
                    onClick={() => setMobileMenuOpen(false)}
                    className="glass-btn-primary flex items-center justify-center px-[var(--space-16)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)] text-center no-underline"
                  >
                    {canAccessApp ? 'Приложение' : 'Открыть приложение'}
                  </Link>
                )
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-[var(--space-8)]">
              <button
                onClick={() => { setMobileMenuOpen(false); onLoginClick?.(); }}
                className="flex items-center gap-[var(--space-10)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)] hover:bg-[rgba(255,255,255,0.06)] transition-all cursor-pointer"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none" className="text-[var(--color-brand-primary)]"><path d="M10 2h2.667A1.333 1.333 0 0114 3.333v9.334A1.333 1.333 0 0112.667 14H10M6.667 11.333L10 8m0 0L6.667 4.667M10 8H2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Войти
              </button>
              {mode !== 'app' && (
                onCtaClick ? (
                  <button
                    onClick={() => { setMobileMenuOpen(false); onCtaClick(); }}
                    className="glass-btn-primary flex items-center justify-center px-[var(--space-16)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)] text-center cursor-pointer"
                  >
                    Попробовать
                  </button>
                ) : (
                  <Link
                    to="/app"
                    onClick={() => setMobileMenuOpen(false)}
                    className="glass-btn-primary flex items-center justify-center px-[var(--space-16)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)] text-center no-underline"
                  >
                    Попробовать
                  </Link>
                )
              )}
            </div>
          )}

          <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />

          <button className="glass-btn-ghost flex items-center gap-[var(--space-10)] px-[var(--space-12)] py-[var(--space-12)] text-[16px] leading-[24px] font-medium text-[#E6EEF8] rounded-[var(--radius-12)]">
            <GlobeIcon size={20} className="text-[var(--color-text-muted)]" />
            Русский
          </button>
        </motion.div>
      )}
    </AnimatePresence>
    </>
  );
}
