import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import * as api from '../../lib/api';
import { useApp } from '../../context/AppContext';

interface Props {
  open: boolean;
  onClose: () => void;
  styleId: string;
  onApply: (hints: Record<string, any>) => void;
}

interface StyleOptions {
  lighting?: string[];
  scene?: string[];
  clothing?: string[];
  framing?: string[];
}

// v1.26: RU-словари для known-значений. Значения в styles.json — это
// свободные английские фразы ("soft morning light, cool river tones").
// Полностью словарь не закрыть, поэтому стратегия такая: known ключи
// (например, 'golden hour', 'studio') отдаём RU, остальное показываем
// как есть, с capitalize — пользователь хотя бы узнает, что выбрал.
const LIGHTING_LABELS_RU: Record<string, string> = {
  'golden hour': 'Золотой час',
  'studio': 'Студийный свет',
  'overcast': 'Мягкий рассеянный',
  'blue hour': 'Синий час',
  'morning': 'Утреннее',
  'sunset': 'Закат',
  'twilight': 'Сумерки',
};

const FRAMING_LABELS_RU: Record<string, string> = {
  portrait: 'Портрет (голова и плечи)',
  half_body: 'По пояс',
  full_body: 'В полный рост',
};

const CATEGORY_LABELS_RU: Record<string, string> = {
  lighting: 'Освещение',
  scene: 'Сцена / локация',
  clothing: 'Одежда',
  framing: 'Ракурс',
};

function capitalize(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function labelFor(channel: string, value: string): string {
  if (channel === 'framing') {
    return FRAMING_LABELS_RU[value] ?? capitalize(value);
  }
  if (channel === 'lighting') {
    const lc = value.toLowerCase();
    for (const [key, ru] of Object.entries(LIGHTING_LABELS_RU)) {
      if (lc.includes(key)) return ru;
    }
    return capitalize(value);
  }
  return capitalize(value);
}

export default function StyleSettingsModal({ open, onClose, styleId, onApply }: Props) {
  const app = useApp();
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<StyleOptions | null>(null);
  const [hints, setHints] = useState<Record<string, any>>({});

  const styleName = useMemo(() => {
    const style = app.effectiveStyleList.find((s) => s.key === styleId);
    return style?.name ?? '';
  }, [app.effectiveStyleList, styleId]);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setHints({});
      return;
    }
    if (!styleId) return;
    setLoading(true);
    api.getStyleOptions(styleId)
      .then(res => {
        setOptions((res.options ?? {}) as StyleOptions);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setOptions({});
        setLoading(false);
      });
  }, [open, styleId]);

  if (!open) return null;

  const hasLighting = !!options?.lighting && options.lighting.length > 0;
  const hasScene = !!options?.scene && options.scene.length > 0;
  const hasClothing = !!options?.clothing && options.clothing.length > 0;
  const hasFraming = !!options?.framing && options.framing.length > 0;
  const hasAnyField = hasLighting || hasScene || hasClothing || hasFraming;

  return createPortal(
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[9999] flex items-end tablet:items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      >
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

        <motion.div
          className="relative gradient-border-card glass-card w-full max-w-[520px] rounded-t-[var(--radius-16)] tablet:rounded-[var(--radius-16)] tablet:mb-6 flex flex-col overflow-hidden"
          style={{ maxHeight: '85dvh' }}
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', damping: 32, stiffness: 320 }}
        >
          <div className="shrink-0 flex flex-col items-center pt-[var(--space-8)] pb-[var(--space-4)] tablet:hidden">
            <div className="w-10 h-1 rounded-full bg-[rgba(255,255,255,0.2)]" />
          </div>

          <div className="shrink-0 flex items-start justify-between px-[var(--space-16)] pt-[var(--space-8)] tablet:pt-[var(--space-16)] pb-[var(--space-8)]">
            <div className="flex flex-col min-w-0">
              <span className="text-[16px] leading-[22px] font-semibold text-[#E6EEF8]">
                Настройки стиля
              </span>
              {styleName && (
                <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] truncate">
                  {styleName}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Закрыть"
              className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
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
            ) : !hasAnyField ? (
              <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-16)]">
                Этот стиль не поддерживает дополнительные настройки.
              </div>
            ) : (
              <>
                {hasLighting && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.lighting}
                    </span>
                    <select
                      value={hints.lighting ?? ''}
                      onChange={(e) => setHints((h) => ({ ...h, lighting: e.target.value }))}
                      className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[#E6EEF8]"
                    >
                      <option value="">По умолчанию</option>
                      {options!.lighting!.map((opt) => (
                        <option key={opt} value={opt}>{labelFor('lighting', opt)}</option>
                      ))}
                    </select>
                  </div>
                )}

                {hasFraming && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.framing}
                    </span>
                    <div className="flex flex-wrap gap-[var(--space-4)]">
                      {options!.framing!.map((opt) => {
                        const active = (hints.framing ?? '') === opt;
                        return (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setHints((h) => ({
                              ...h,
                              framing: active ? '' : opt,
                            }))}
                            className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                              active
                                ? 'glass-btn-primary text-white'
                                : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                            }`}
                          >
                            {labelFor('framing', opt)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {hasScene && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.scene}
                    </span>
                    <input
                      type="text"
                      placeholder="Например: на фоне гор"
                      value={hints.scene_override ?? ''}
                      onChange={(e) => setHints((h) => ({ ...h, scene_override: e.target.value }))}
                      className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[#E6EEF8]"
                    />
                    {options!.scene!.length > 0 && (
                      <div className="flex flex-wrap gap-[var(--space-4)]">
                        {options!.scene!.slice(0, 6).map((opt) => (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setHints((h) => ({ ...h, scene_override: opt }))}
                            className="px-[var(--space-10)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[16px] font-medium glass-btn-ghost text-[var(--color-text-secondary)]"
                          >
                            {capitalize(opt)}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {hasClothing && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.clothing}
                    </span>
                    <input
                      type="text"
                      placeholder="Например: красный костюм"
                      value={hints.clothing_override ?? ''}
                      onChange={(e) => setHints((h) => ({ ...h, clothing_override: e.target.value }))}
                      className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[#E6EEF8]"
                    />
                    {options!.clothing!.length > 0 && (
                      <div className="flex flex-wrap gap-[var(--space-4)]">
                        {options!.clothing!.slice(0, 6).map((opt) => (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setHints((h) => ({ ...h, clothing_override: opt }))}
                            className="px-[var(--space-10)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[16px] font-medium glass-btn-ghost text-[var(--color-text-secondary)]"
                          >
                            {capitalize(opt)}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            <button
              type="button"
              onClick={() => {
                const cleaned: Record<string, any> = {};
                for (const [key, value] of Object.entries(hints)) {
                  if (typeof value === 'string' && value.trim()) {
                    cleaned[key] = value.trim();
                  } else if (value !== '' && value != null) {
                    cleaned[key] = value;
                  }
                }
                onApply(cleaned);
                onClose();
              }}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium mt-[var(--space-4)]"
            >
              Применить и сгенерировать
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}
