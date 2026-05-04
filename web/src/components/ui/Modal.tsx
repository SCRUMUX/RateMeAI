import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import type { ReactNode } from 'react';
import Card from './Card';

/**
 * 1.33.0 — token-driven Modal primitive.
 *
 * Wraps the (otherwise-duplicated) backdrop + framer-motion + portal
 * + esc-to-close + body-scroll-lock plumbing currently copy-pasted
 * across AuthModal / StorageModal / ReviewModal / ShareModal /
 * StyleSettingsModal. Caller is responsible for the actual content
 * inside ``children``.
 *
 * Uses ``Card variant="gradient-border"`` for the surface so the
 * modal inherits the same theming hooks as the rest of the design
 * system. ``size`` defaults to ``"md"`` (max-width 480px); ``"sm"``
 * is used for confirmation dialogs (320px) and ``"lg"`` for forms
 * with rich content (640px).
 */

type ModalSize = 'sm' | 'md' | 'lg';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** When true, esc / backdrop click do nothing — caller must
   *  drive close some other way (e.g. successful submit). */
  required?: boolean;
  size?: ModalSize;
  /** Optional title rendered with consistent typography at the top
   *  of the modal. Caller may also render its own header inside
   *  ``children`` and skip this prop. */
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** Override surface variant. Defaults to ``gradient-border``. */
  variant?: 'glass' | 'solid' | 'gradient-border';
  /** Tailwind className applied to the inner card. */
  className?: string;
}

const SIZE_CLASS: Record<ModalSize, string> = {
  sm: 'max-w-[320px]',
  md: 'max-w-[480px]',
  lg: 'max-w-[640px]',
};

export default function Modal({
  open,
  onClose,
  required,
  size = 'md',
  title,
  description,
  children,
  variant = 'gradient-border',
  className = '',
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !required) onClose();
    }
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose, required]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[9999] flex items-center justify-center p-[var(--space-24)]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div
            className="absolute inset-0 bg-[var(--effect-scrim-strong)] backdrop-blur-sm"
            onClick={required ? undefined : onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
            className={`relative w-full ${SIZE_CLASS[size]}`}
          >
            <Card
              variant={variant}
              role="dialog"
              aria-modal="true"
              className={`p-[var(--space-32)] flex flex-col gap-[var(--space-24)] ${className}`}
            >
              {!required && (
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть"
                  className="absolute top-[var(--space-16)] right-[var(--space-16)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              )}
              {(title || description) && (
                <div className="flex flex-col gap-[var(--space-8)] text-center">
                  {title && (
                    <h3 className="text-[24px] leading-[32px] font-semibold text-[var(--color-text-primary)]">
                      {title}
                    </h3>
                  )}
                  {description && (
                    <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">
                      {description}
                    </p>
                  )}
                </div>
              )}
              {children}
            </Card>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
