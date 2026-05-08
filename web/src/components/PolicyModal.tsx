import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { getPolicy, type PolicyId } from '../data/policies';
import useFocusTrap from '../lib/useFocusTrap';
import { useApp } from '../context/AppContext';

interface Props {
  open: boolean;
  policyId: PolicyId | string | null;
  onClose: () => void;
}

export default function PolicyModal({ open, policyId, onClose }: Props) {
  const entry = getPolicy(policyId ?? null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useFocusTrap(open && entry !== null, dialogRef);
  const { activeCategory } = useApp();
  const { t } = useTranslation('modals');

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && entry && (
        <motion.div
          data-category={activeCategory}
          className="fixed inset-0 z-[9999] flex items-center justify-center p-[var(--space-16)] tablet:p-[var(--space-24)]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

          <motion.div
            ref={dialogRef}
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[820px] max-h-[88vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`policy-${entry.id}-title`}
          >
            <header className="flex items-start justify-between gap-[var(--space-12)] px-[var(--space-20)] tablet:px-[var(--space-32)] pt-[var(--space-20)] tablet:pt-[var(--space-24)] pb-[var(--space-12)] border-b border-white/10">
              <div className="flex flex-col">
                <h2
                  id={`policy-${entry.id}-title`}
                  className="text-[20px] tablet:text-[26px] font-semibold leading-[1.2] text-[var(--color-text-primary)]"
                >
                  {entry.title}
                </h2>
                <p className="text-[12px] text-[var(--color-text-muted)] mt-[var(--space-4)]">
                  {t('policy.lastUpdated', { date: entry.lastUpdated })}
                </p>
              </div>
              <button
                onClick={onClose}
                aria-label={t('common.close')}
                className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </header>

            <article className="overflow-y-auto px-[var(--space-20)] tablet:px-[var(--space-32)] py-[var(--space-20)] tablet:py-[var(--space-24)] text-[14px] tablet:text-[15px] leading-[1.7] text-[var(--color-text-secondary)] space-y-[var(--space-16)]">
              {entry.body}
            </article>

            <footer className="flex items-center justify-between gap-[var(--space-12)] px-[var(--space-20)] tablet:px-[var(--space-32)] py-[var(--space-12)] border-t border-white/10">
              {entry.id === 'privacy' ? (
                <Link
                  to="/privacy"
                  className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors no-underline"
                  onClick={onClose}
                >
                  {t('policy.openSeparate')}
                </Link>
              ) : (
                <span />
              )}
              <button
                onClick={onClose}
                className="glass-btn-secondary px-[var(--space-20)] py-[var(--space-8)] rounded-[var(--radius-12)] text-[14px] leading-[20px] text-[var(--color-text-primary)]"
              >
                {t('common.close')}
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
