import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import * as api from '../../lib/api';

interface Props {
  open: boolean;
  onClose: () => void;
  styleId: string;
  onApply: (hints: Record<string, any>) => void;
}

export default function StyleSettingsModal({ open, onClose, styleId, onApply }: Props) {
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<any>(null);
  const [hints, setHints] = useState<Record<string, any>>({});

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    if (!open || !styleId) return;
    setLoading(true);
    api.getStyleOptions(styleId)
      .then(res => {
        setOptions(res.options);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setLoading(false);
      });
  }, [open, styleId]);

  if (!open) return null;

  return createPortal(
    <AnimatePresence>
      <motion.div
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
          <div className="shrink-0 flex flex-col items-center pt-[var(--space-8)] pb-[var(--space-4)]">
            <div className="w-10 h-1 rounded-full bg-[rgba(255,255,255,0.2)]" />
          </div>
          <div className="shrink-0 flex items-center justify-between px-[var(--space-16)] py-[var(--space-8)]">
            <span className="text-[16px] leading-[24px] font-semibold text-[#E6EEF8]">Настройки стиля</span>
            <button
              onClick={onClose}
              className="w-9 h-9 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
            >
              <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-[var(--space-16)] pb-[var(--space-16)] flex flex-col gap-[var(--space-16)]">
            {loading ? (
              <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-16)]">
                Загрузка настроек...
              </div>
            ) : (
              <>
                {options?.lighting?.length > 0 && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">Освещение</span>
                    <select
                      value={hints.lighting || ''}
                      onChange={e => setHints(h => ({ ...h, lighting: e.target.value }))}
                      className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[#E6EEF8]"
                    >
                      <option value="">По умолчанию</option>
                      {options.lighting.map((opt: string) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="flex flex-col gap-[var(--space-8)]">
                  <span className="text-[13px] font-medium text-[var(--color-text-muted)]">Одежда (кастомная)</span>
                  <input
                    type="text"
                    placeholder="Например: красный костюм"
                    value={hints.clothing_override || ''}
                    onChange={e => setHints(h => ({ ...h, clothing_override: e.target.value }))}
                    className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[#E6EEF8]"
                  />
                </div>

                <div className="flex flex-col gap-[var(--space-8)]">
                  <span className="text-[13px] font-medium text-[var(--color-text-muted)]">Локация (кастомная)</span>
                  <input
                    type="text"
                    placeholder="Например: на фоне гор"
                    value={hints.scene_override || ''}
                    onChange={e => setHints(h => ({ ...h, scene_override: e.target.value }))}
                    className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[#E6EEF8]"
                  />
                </div>
              </>
            )}

            <button
              onClick={() => {
                onApply(hints);
                onClose();
              }}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium mt-4"
            >
              Применить и сгенерировать
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}