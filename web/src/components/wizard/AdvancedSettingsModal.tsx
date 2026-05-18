import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useApp } from '../../context/AppContext';

/**
 * Composition Safety Layer (CSL) — advanced override modal.
 *
 * Phase 3 of the CSL rollout. Behind ``VITE_COMPOSITION_OVERRIDE_ENABLED``
 * because the backend's ``settings.composition_safety_advanced_override``
 * must also be flipped on the deployment for the override to actually
 * take effect — gating the UI on the same flag (passed via Vite env)
 * stops users from staring at a toggle that does nothing.
 *
 * The flow is two-step on purpose: the user sees the explicit warning
 * text, has to acknowledge it, and only *then* does the wizard send
 * ``skip_composition_safety=true`` on the next generate call. The
 * choice is one-shot (resets on photo reupload) so it can't leak into
 * an unrelated future session.
 */
interface Props {
  open: boolean;
  onClose: () => void;
}

const OVERRIDE_ENABLED = (
  (import.meta as any)?.env?.VITE_COMPOSITION_OVERRIDE_ENABLED ?? 'false'
) === 'true';

export default function AdvancedSettingsModal({ open, onClose }: Props) {
  const app = useApp();
  const { t } = useTranslation('wizard');

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!OVERRIDE_ENABLED) {
    // The build-time flag is off — render nothing so the trigger
    // button never lights up either. A static return is preferable to
    // a runtime feature-detect inside the parent because it lets
    // tree-shaking drop the whole modal on builds that don't enable
    // it.
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="advanced-settings-modal"
          className="fixed inset-0 z-[9999] flex items-end tablet:items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />

          <motion.div
            className="relative gradient-border-card glass-card w-full max-w-[480px] rounded-t-[var(--radius-16)] tablet:rounded-[var(--radius-16)] flex flex-col overflow-hidden"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 32, stiffness: 320 }}
          >
            <div className="shrink-0 flex items-center justify-between px-[var(--space-16)] py-[var(--space-12)] border-b border-[var(--glass-border-soft)]">
              <span className="text-[16px] leading-[24px] font-semibold text-[var(--color-text-primary)]">
                {t('advancedSettings.title')}
              </span>
              <button
                onClick={onClose}
                aria-label={t('advancedSettings.close')}
                className="w-9 h-9 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
                type="button"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M4 4L12 12M12 4L4 12"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>

            <div className="flex flex-col gap-[var(--space-12)] p-[var(--space-16)]">
              <div className="flex items-start gap-[var(--space-8)] p-[var(--space-12)] rounded-[var(--radius-12)] bg-[var(--glass-surface-soft)]">
                <span aria-hidden className="text-[18px] leading-none">⚠️</span>
                <p className="text-[13px] leading-[18px] text-[var(--color-text-secondary)]">
                  {t('advancedSettings.warning')}
                </p>
              </div>

              <label className="flex items-start gap-[var(--space-10)] cursor-pointer">
                <input
                  type="checkbox"
                  checked={app.skipCompositionSafety}
                  onChange={(e) => app.setSkipCompositionSafety(e.target.checked)}
                  className="mt-[2px] w-4 h-4 accent-[var(--color-warning-base)]"
                />
                <span className="flex flex-col gap-[2px]">
                  <span className="text-[14px] leading-[20px] font-medium text-[var(--color-text-primary)]">
                    {t('advancedSettings.skipLabel')}
                  </span>
                  <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)]">
                    {t('advancedSettings.skipHelp')}
                  </span>
                </span>
              </label>

              <button
                type="button"
                onClick={onClose}
                className="glass-btn-primary w-full py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] font-medium"
              >
                {t('advancedSettings.confirm')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
