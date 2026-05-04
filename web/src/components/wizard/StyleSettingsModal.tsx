import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import * as api from '../../lib/api';
import { useApp } from '../../context/AppContext';

// 1.31.0 — local popover-dropdown to replace the native <select>.
// The native control inherits the OS menu styling, which on Windows
// renders as a white opaque list on top of our dark theme. This
// component reuses the existing `glass-card` / `glass-btn-*` classes
// so it stays consistent with the rest of the wizard, and respects
// `data-theme` automatically. We keep it local here for now; in
// Wave 2 (1.32.0) it will be extracted into `components/ui/Select.tsx`.
interface DropdownOption {
  value: string;
  label: string;
}

interface DropdownProps {
  value: string;
  options: DropdownOption[];
  placeholder: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
}

function Dropdown({ value, options, placeholder, onChange, ariaLabel }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleMouseDown(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleMouseDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const currentLabel = options.find((o) => o.value === value)?.label ?? placeholder;

  return (
    <div ref={containerRef} className="relative w-full">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full bg-surface-2 border border-border-base rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-text-primary text-left flex items-center justify-between gap-[var(--space-8)]"
      >
        <span className={`truncate ${value ? '' : 'text-[var(--color-text-muted)]'}`}>
          {currentLabel}
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
          className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+4px)] z-10 glass-card rounded-[var(--radius-8)] border border-border-base p-[var(--space-4)] flex flex-col gap-[2px] max-h-[240px] overflow-y-auto"
        >
          {options.map((opt) => {
            const active = opt.value === value;
            return (
              <button
                key={opt.value || '__placeholder__'}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`w-full text-left px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-md)] text-[14px] leading-[20px] transition-colors ${
                  active
                    ? 'bg-surface-3 text-text-primary'
                    : 'text-text-primary hover:bg-surface-2'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  styleId: string;
  onApply: (hints: Record<string, any>) => void;
}

// Stage 3 (2026-05) — the modal is unified across schema versions.
// It always renders a v3-shaped slot map; v2 / v1 payloads are
// projected onto the same shape so the UI doesn't have to branch on
// schema_version. Channels with no candidate values are simply
// hidden (we never render an empty selector).
//
// ``triggerPool`` is read-only: it is the immutable headline motif of
// the style ("Burj Khalifa", "full-length mirror reflection") and the
// slot sampler is guaranteed to drop one of these into every prompt.
// The user can pick lighting/weather/etc. but cannot opt out of the
// trigger — that's the contract that makes "У зеркала" actually show
// a mirror.
interface StyleOptions {
  triggerPool: string[];
  sceneAnchor: string;
  sceneOverrides: string[];
  lighting: string[];
  weather: string[];
  timeOfDay: string[];
  season: string[];
  clothing: string[];
  framing: string[];
  sceneLocked: boolean;
  weatherEnabled: boolean;
  // 1.29.0 — explicit list of channels surfaced to the user. Empty
  // means "не курировано", the modal falls back to "show channel iff
  // its pool is non-empty" (legacy 1.28 behaviour).
  availableChannels: string[];
  locationType: string;
  // Backwards-compat marker for the analytics layer.
  schemaVersion: 1 | 2 | 3;
}

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

const WEATHER_LABELS_RU: Record<string, string> = {
  clear: 'Ясно',
  sunny: 'Солнечно',
  overcast: 'Пасмурно',
  cloudy: 'Облачно',
  rain: 'Дождь',
  rainy: 'Дождь',
  snow: 'Снег',
  fog: 'Туман',
  mist: 'Дымка',
  windy: 'Ветрено',
  storm: 'Шторм',
};

const TIME_OF_DAY_LABELS_RU: Record<string, string> = {
  dawn: 'Рассвет',
  morning: 'Утро',
  noon: 'Полдень',
  afternoon: 'День',
  evening: 'Вечер',
  sunset: 'Закат',
  dusk: 'Сумерки',
  twilight: 'Сумерки',
  'blue hour': 'Синий час',
  'golden hour': 'Золотой час',
  night: 'Ночь',
  midnight: 'Полночь',
};

const SEASON_LABELS_RU: Record<string, string> = {
  spring: 'Весна',
  summer: 'Лето',
  autumn: 'Осень',
  fall: 'Осень',
  winter: 'Зима',
};

const CATEGORY_LABELS_RU: Record<string, string> = {
  lighting: 'Освещение',
  scene: 'Сцена / локация',
  clothing: 'Одежда',
  framing: 'Ракурс',
  weather: 'Погода',
  time_of_day: 'Время суток',
  season: 'Сезон',
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
  if (channel === 'weather') {
    return WEATHER_LABELS_RU[value.toLowerCase()] ?? capitalize(value);
  }
  if (channel === 'time_of_day') {
    const lc = value.toLowerCase();
    return TIME_OF_DAY_LABELS_RU[lc] ?? capitalize(value);
  }
  if (channel === 'season') {
    const lc = value.toLowerCase();
    return SEASON_LABELS_RU[lc] ?? capitalize(value);
  }
  return capitalize(value);
}

// Project a v3 payload directly onto StyleOptions. Trivial — v3 is
// the canonical shape we render against.
function fromV3(v3: api.StyleOptionsV3Payload): StyleOptions {
  const availableChannels: string[] = Array.isArray(v3.available_channels)
    ? (v3.available_channels as string[]).filter((c) => typeof c === 'string')
    : [];
  return {
    triggerPool: Array.isArray(v3.trigger_pool) ? v3.trigger_pool : [],
    sceneAnchor: v3.scene_anchor ?? '',
    sceneOverrides: Array.isArray(v3.scene_overrides) ? v3.scene_overrides : [],
    lighting: v3.ambient?.lighting ?? [],
    weather: v3.ambient?.weather ?? [],
    timeOfDay: v3.ambient?.time_of_day ?? [],
    season: v3.ambient?.season ?? [],
    clothing: v3.clothing?.allowed ?? [],
    framing: Array.isArray(v3.framing) ? v3.framing : [],
    sceneLocked: v3.background_lock === 'locked',
    weatherEnabled: availableChannels.length > 0
      ? availableChannels.includes('weather')
      : (v3.ambient?.weather?.length ?? 0) > 0,
    availableChannels,
    locationType: typeof v3.location_type === 'string' ? v3.location_type : '',
    schemaVersion: 3,
  };
}

// v2 → StyleOptions: keeps the modal usable if the catalog endpoint
// transparently downgrades for an unmigrated style. The v2 row has
// no ``trigger_pool``, only a single ``trigger`` string — we wrap it
// into a one-element pool so the read-only badge still renders.
function fromV2(v2: api.StyleOptionsV2Payload): StyleOptions {
  return {
    triggerPool: v2.trigger ? [v2.trigger] : [],
    sceneAnchor: v2.background?.base ?? '',
    sceneOverrides: v2.background?.overrides_allowed ?? [],
    lighting: v2.context_slots?.lighting ?? [],
    weather: v2.weather?.allowed ?? [],
    timeOfDay: v2.context_slots?.time_of_day ?? [],
    season: v2.context_slots?.season ?? [],
    clothing: v2.clothing?.allowed ?? [],
    framing: v2.context_slots?.framing ?? [],
    sceneLocked: v2.background?.lock === 'locked',
    weatherEnabled: !!v2.weather?.enabled,
    availableChannels: [],
    locationType: '',
    schemaVersion: 2,
  };
}

function fromV1(v1: Record<string, string[]>): StyleOptions {
  return {
    triggerPool: [],
    sceneAnchor: '',
    sceneOverrides: v1.scene ?? [],
    lighting: v1.lighting ?? [],
    weather: [],
    timeOfDay: [],
    season: [],
    clothing: v1.clothing ?? [],
    framing: v1.framing ?? [],
    sceneLocked: false,
    weatherEnabled: false,
    availableChannels: [],
    locationType: '',
    schemaVersion: 1,
  };
}

function normaliseOptions(res: api.StyleOptionsResponse): StyleOptions {
  if (res.schema_version === 3) {
    return fromV3(res.options as api.StyleOptionsV3Payload);
  }
  if (res.schema_version === 2) {
    return fromV2(res.options as api.StyleOptionsV2Payload);
  }
  return fromV1((res.options ?? {}) as Record<string, string[]>);
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

  // The "headline" trigger to show in the read-only badge. We pick
  // the first formulation from the pool because it's the canonical
  // / shortest variant (curated.json ordering); the slot sampler will
  // still pick a random one per generation, but the badge needs a
  // stable display string.
  const triggerHeadline = useMemo(() => {
    const pool = options?.triggerPool ?? [];
    return pool.length > 0 ? pool[0] : '';
  }, [options]);

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
        setOptions(normaliseOptions(res));
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setOptions(null);
        setLoading(false);
      });
  }, [open, styleId]);

  if (!open) return null;

  // 1.29.0 — when the operator has curated ``available_channels``,
  // a channel is shown iff it appears in that list AND has a non-empty
  // pool. Otherwise we keep the legacy behaviour ("non-empty pool ⇒
  // visible") so the 126 styles already on disk continue to work.
  const curatedChannels = options?.availableChannels ?? [];
  const isCurated = curatedChannels.length > 0;
  const channelOn = (channel: string, hasValues: boolean): boolean => {
    if (!isCurated) return hasValues;
    return curatedChannels.includes(channel) && hasValues;
  };

  const hasTrigger = !!triggerHeadline;
  const hasLighting = channelOn('lighting', (options?.lighting?.length ?? 0) > 0);
  const hasTimeOfDay = channelOn('time_of_day', (options?.timeOfDay?.length ?? 0) > 0);
  const hasSeason = channelOn('season', (options?.season?.length ?? 0) > 0);
  // The Scene section is hidden when background is hard-locked
  // (passport / document styles) OR when the operator gated off the
  // ``scene_override`` channel.
  const hasScene =
    !!options &&
    !options.sceneLocked &&
    (isCurated ? curatedChannels.includes('scene_override') : true);
  const hasClothing = channelOn('clothing', (options?.clothing?.length ?? 0) > 0);
  // Framing falls back to the three default chips even with empty pool,
  // so we only hide it when the operator explicitly disabled the channel.
  const hasFraming = isCurated
    ? curatedChannels.includes('framing') && (options?.framing?.length ?? 0) > 0
    : (options?.framing?.length ?? 0) > 0;
  const hasWeather = channelOn('weather', !!options?.weatherEnabled);
  const hasAnyField =
    hasLighting ||
    hasTimeOfDay ||
    hasSeason ||
    hasScene ||
    hasClothing ||
    hasFraming ||
    hasWeather;

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
            <div className="w-10 h-1 rounded-full bg-border-strong" />
          </div>

          <div className="shrink-0 flex items-start justify-between px-[var(--space-16)] pt-[var(--space-8)] tablet:pt-[var(--space-16)] pb-[var(--space-8)]">
            <div className="flex flex-col min-w-0">
              <span className="text-[16px] leading-[22px] font-semibold text-text-primary">
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
              className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-text-primary transition-colors"
            >
              <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-[var(--space-16)] pb-[var(--space-16)] flex flex-col gap-[var(--space-16)]">
            {hasTrigger && (
              <div
                className="flex items-start gap-[var(--space-8)] rounded-[var(--radius-12)] px-[var(--space-12)] py-[var(--space-8)] bg-brand-primary/10 border border-brand-primary/30"
                title="Этот элемент всегда в кадре. Изменить нельзя."
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  className="shrink-0 mt-[1px] text-brand-primary"
                >
                  <path
                    d="M8 1.5L9.94 5.43L14.27 6.06L11.13 9.12L11.87 13.43L8 11.4L4.13 13.43L4.87 9.12L1.73 6.06L6.06 5.43L8 1.5Z"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinejoin="round"
                  />
                </svg>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-[11px] uppercase tracking-wider text-brand-primary font-medium">
                    Триггер стиля
                  </span>
                  <span className="text-[13px] leading-[18px] text-text-primary truncate">
                    {triggerHeadline}
                  </span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] mt-[2px]">
                    Всегда в кадре. Изменить нельзя.
                  </span>
                </div>
              </div>
            )}

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
                    <Dropdown
                      ariaLabel={CATEGORY_LABELS_RU.lighting}
                      value={hints.lighting ?? ''}
                      placeholder="Авто (рандом)"
                      onChange={(v) => setHints((h) => ({ ...h, lighting: v }))}
                      options={[
                        { value: '', label: 'Авто (рандом)' },
                        ...options!.lighting!.map((opt) => ({
                          value: opt,
                          label: labelFor('lighting', opt),
                        })),
                      ]}
                    />
                  </div>
                )}

                {hasTimeOfDay && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.time_of_day}
                    </span>
                    <div className="flex flex-wrap gap-[var(--space-4)]">
                      <button
                        key="__auto__"
                        type="button"
                        onClick={() => setHints((h) => ({ ...h, time_of_day: '' }))}
                        className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                          (hints.time_of_day ?? '') === ''
                            ? 'glass-btn-primary text-white'
                            : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                        }`}
                      >
                        Авто (рандом)
                      </button>
                      {options!.timeOfDay!.map((opt) => {
                        const active = (hints.time_of_day ?? '') === opt;
                        return (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setHints((h) => ({
                              ...h,
                              time_of_day: active ? '' : opt,
                            }))}
                            className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                              active
                                ? 'glass-btn-primary text-white'
                                : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                            }`}
                          >
                            {labelFor('time_of_day', opt)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {hasSeason && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.season}
                    </span>
                    <div className="flex flex-wrap gap-[var(--space-4)]">
                      <button
                        key="__auto__"
                        type="button"
                        onClick={() => setHints((h) => ({ ...h, season: '' }))}
                        className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                          (hints.season ?? '') === ''
                            ? 'glass-btn-primary text-white'
                            : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                        }`}
                      >
                        Авто (рандом)
                      </button>
                      {options!.season!.map((opt) => {
                        const active = (hints.season ?? '') === opt;
                        return (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setHints((h) => ({
                              ...h,
                              season: active ? '' : opt,
                            }))}
                            className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                              active
                                ? 'glass-btn-primary text-white'
                                : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                            }`}
                          >
                            {labelFor('season', opt)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {hasFraming && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.framing}
                    </span>
                    <div className="flex flex-wrap gap-[var(--space-4)]">
                      <button
                        key="__default__"
                        type="button"
                        onClick={() => setHints((h) => ({ ...h, framing: '' }))}
                        className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                          (hints.framing ?? '') === ''
                            ? 'glass-btn-primary text-white'
                            : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                        }`}
                        title="Использовать ракурс из шага «Выберите стиль»"
                      >
                        По умолчанию
                      </button>
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
                      className="w-full bg-surface-2 border border-border-base rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-text-primary placeholder:text-[var(--color-text-muted)]"
                    />
                    {(options!.sceneOverrides?.length ?? 0) > 0 && (
                      <div className="flex flex-wrap gap-[var(--space-4)]">
                        {options!.sceneOverrides!.slice(0, 6).map((opt) => (
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
                      className="w-full bg-surface-2 border border-border-base rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-text-primary placeholder:text-[var(--color-text-muted)]"
                    />
                    {(options!.clothing?.length ?? 0) > 0 && (
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

                {hasWeather && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {CATEGORY_LABELS_RU.weather}
                    </span>
                    <div className="flex flex-wrap gap-[var(--space-4)]">
                      <button
                        key="__auto__"
                        type="button"
                        onClick={() => setHints((h) => ({ ...h, weather: '' }))}
                        className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                          (hints.weather ?? '') === ''
                            ? 'glass-btn-primary text-white'
                            : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                        }`}
                      >
                        Авто (рандом)
                      </button>
                      {(options!.weather ?? []).map((opt) => {
                        const active = (hints.weather ?? '') === opt;
                        return (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setHints((h) => ({
                              ...h,
                              weather: active ? '' : opt,
                            }))}
                            className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                              active
                                ? 'glass-btn-primary text-white'
                                : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                            }`}
                          >
                            {labelFor('weather', opt)}
                          </button>
                        );
                      })}
                    </div>
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
