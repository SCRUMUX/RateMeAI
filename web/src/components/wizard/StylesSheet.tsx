import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { getMockDelta, type StyleItem } from '../../data/styles';
import { orderStylesByLock } from './lockedStyles';

interface Props {
  open: boolean;
  onClose: () => void;
  styles: readonly StyleItem[];
  selectedKey: string;
  lockedKeys: Set<string>;
  onPick: (key: string) => void;
}

export default function StylesSheet({ open, onClose, styles, selectedKey, lockedKeys, onPick }: Props) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  const ordered = orderStylesByLock(styles, lockedKeys);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="styles-sheet"
          className="fixed inset-0 z-[9999] flex items-end justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

          <motion.div
            className="relative gradient-border-card glass-card w-full max-w-[560px] rounded-t-[var(--radius-16)] tablet:rounded-[var(--radius-16)] tablet:mb-6 flex flex-col overflow-hidden"
            style={{ maxHeight: '85dvh' }}
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 32, stiffness: 320 }}
          >
            {/* Drag handle + header */}
            <div className="shrink-0 flex flex-col items-center pt-[var(--space-8)] pb-[var(--space-4)]">
              <div className="w-10 h-1 rounded-full bg-[rgba(255,255,255,0.2)]" />
            </div>
            <div className="shrink-0 flex items-center justify-between px-[var(--space-16)] py-[var(--space-8)]">
              <span className="text-[16px] leading-[24px] font-semibold text-[#E6EEF8]">Все образы</span>
              <button
                onClick={onClose}
                aria-label="Закрыть"
                className="w-9 h-9 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            {/* Scrollable list (flat — category grouping was retired with the v2 catalog cleanup). */}
            <div className="flex-1 min-h-0 overflow-y-auto px-[var(--space-16)] pb-[var(--space-16)] flex flex-col gap-[var(--space-8)]">
              {ordered.map((s) => {
                const locked = lockedKeys.has(s.key);
                const selected = !locked && s.key === selectedKey;
                const lockBadge = s.unlock_after_generations
                  ? `Доступно после ${s.unlock_after_generations} генераций`
                  : 'Скоро доступно';
                return (
                  <button
                    key={s.key}
                    type="button"
                    disabled={locked}
                    onClick={() => { if (!locked) { onPick(s.key); onClose(); } }}
                    className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-10)] gap-[var(--space-8)] min-h-[48px] rounded-[var(--radius-12)] transition-all text-left ${
                      locked ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                    } ${selected ? 'glass-row-active' : 'glass-row'}`}
                    style={{
                      '--gb-color': selected
                        ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)'
                        : 'rgba(255, 255, 255, 0.10)',
                    } as React.CSSProperties}
                  >
                    <div className="flex items-center justify-center w-6 h-6 shrink-0 text-[20px] leading-none relative">
                      {locked ? (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-[var(--color-text-muted)]">
                          <rect x="3" y="7" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
                          <path d="M5.5 7V5a2.5 2.5 0 1 1 5 0v2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                        </svg>
                      ) : s.icon}
                    </div>
                    <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                      <span className="text-[15px] leading-[20px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">
                        {locked ? lockBadge : s.desc}
                      </span>
                    </div>
                    {!locked && (
                      <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[13px] leading-[18px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                        {getMockDelta(s.deltaRange, s.key)}
                      </span>
                    )}
                    {locked && (
                      <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[11px] leading-[14px] text-[var(--color-text-muted)] font-medium bg-[rgba(255,255,255,0.06)] shrink-0">
                        Скоро
                      </span>
                    )}
                  </button>
                );
              })}
              {ordered.length === 0 && (
                <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-16)]">
                  Нет доступных стилей
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
