import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import useFocusTrap from '../lib/useFocusTrap';
import { useApp } from '../context/AppContext';

interface FaqItem {
  q: string;
  a: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  telegramUrl?: string;
  email?: string;
  faq?: FaqItem[];
}

const DEFAULT_TELEGRAM_URL = 'https://t.me/ailookstudio_support';
const DEFAULT_EMAIL = 'support@ailookstudio.ru';

export default function SupportModal({
  open,
  onClose,
  telegramUrl,
  email,
  faq,
}: Props) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const { t } = useTranslation('modals');
  const defaultFaq = useMemo<FaqItem[]>(() => {
    const value = t('support.defaultFaq', { returnObjects: true }) as unknown;
    return Array.isArray(value) ? (value as FaqItem[]) : [];
  }, [t]);
  const items = faq && faq.length > 0 ? faq : defaultFaq;
  const tg = (telegramUrl && telegramUrl.trim()) || DEFAULT_TELEGRAM_URL;
  const mail = (email && email.trim()) || DEFAULT_EMAIL;
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useFocusTrap(open, dialogRef);
  const { activeCategory } = useApp();

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
      {open && (
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
            className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[640px] max-h-[88vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="support-modal-title"
          >
            <header className="flex items-start justify-between gap-[var(--space-12)] px-[var(--space-20)] tablet:px-[var(--space-32)] pt-[var(--space-20)] tablet:pt-[var(--space-24)] pb-[var(--space-12)] border-b border-white/10">
              <div className="flex flex-col">
                <h2
                  id="support-modal-title"
                  className="text-[20px] tablet:text-[26px] font-semibold leading-[1.2] text-[var(--color-text-primary)]"
                >
                  {t('support.title')}
                </h2>
                <p className="text-[12px] tablet:text-[13px] text-[var(--color-text-muted)] mt-[var(--space-4)]">
                  {t('support.subtitle')}
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

            <div className="overflow-y-auto px-[var(--space-20)] tablet:px-[var(--space-32)] py-[var(--space-16)] tablet:py-[var(--space-20)] flex flex-col gap-[var(--space-20)]">
              {/* Contact CTAs */}
              <div className="flex flex-col tablet:flex-row gap-[var(--space-12)]">
                <a
                  href={tg}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="glass-btn-primary inline-flex items-center justify-center gap-[var(--space-8)] px-[var(--space-20)] py-[var(--space-12)] rounded-[var(--radius-12)] text-[14px] tablet:text-[15px] leading-[20px] font-medium no-underline flex-1"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M21.94 4.42c.34-1.61-.6-2.27-1.71-1.86L2.71 9.4c-1.18.46-1.16 1.12-.2 1.42l4.5 1.4 10.43-6.59c.49-.32.94-.15.57.18l-8.45 7.62-.32 4.6c.46 0 .67-.21.91-.45l2.18-2.12 4.55 3.36c.83.46 1.43.22 1.65-.77l2.99-14.04z" />
                  </svg>
                  {t('support.ctaTelegram')}
                </a>
                <a
                  href={`mailto:${mail}`}
                  className="glass-btn-secondary inline-flex items-center justify-center gap-[var(--space-8)] px-[var(--space-20)] py-[var(--space-12)] rounded-[var(--radius-12)] text-[14px] tablet:text-[15px] leading-[20px] font-medium no-underline flex-1 text-[var(--color-brand-primary)]"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="M3 7l9 6 9-6" />
                  </svg>
                  {mail}
                </a>
              </div>

              {/* FAQ */}
              <div className="flex flex-col gap-[var(--space-8)]">
                <h3 className="text-[14px] tablet:text-[15px] font-medium text-[var(--color-text-primary)] uppercase tracking-wide opacity-80">
                  {t('support.faqTitle')}
                </h3>
                <ul className="flex flex-col gap-[var(--space-8)]">
                  {items.map((item, i) => {
                    const isOpen = openIdx === i;
                    return (
                      <li
                        key={i}
                        className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02]"
                      >
                        <button
                          type="button"
                          onClick={() => setOpenIdx(isOpen ? null : i)}
                          className="w-full flex items-center justify-between gap-[var(--space-12)] px-[var(--space-16)] py-[var(--space-12)] text-left"
                          aria-expanded={isOpen}
                        >
                          <span className="text-[14px] tablet:text-[15px] leading-[20px] text-[var(--color-text-primary)] font-medium">
                            {item.q}
                          </span>
                          <span
                            className="text-[var(--color-text-muted)] transition-transform"
                            style={{ transform: isOpen ? 'rotate(45deg)' : 'rotate(0deg)' }}
                            aria-hidden="true"
                          >
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                              <path d="M7 1V13M1 7H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                            </svg>
                          </span>
                        </button>
                        {isOpen && (
                          <div className="px-[var(--space-16)] pb-[var(--space-12)] text-[13px] tablet:text-[14px] leading-[20px] text-[var(--color-text-secondary)]">
                            {item.a}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
