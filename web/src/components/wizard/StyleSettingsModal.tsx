import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import * as api from '../../lib/api';
import { useApp } from '../../context/AppContext';
import { Select } from '../ui';

interface Props {
  open: boolean;
  onClose: () => void;
  styleId: string;
  /** Hints to pre-select when the modal opens (e.g. resolved_slots
   * from the last generation). Re-applied every time `open` flips
   * to true so a closed → reopen cycle reflects the latest state. */
  initialHints?: Record<string, any>;
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

const LIGHTING_KEYS = ['golden hour', 'studio', 'overcast', 'blue hour', 'morning', 'sunset', 'twilight'] as const;

function capitalize(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

type LabelTranslate = (key: string, options?: Record<string, unknown>) => string;

function translateOrFallback(t: LabelTranslate, key: string, fallback: string): string {
  const translated = t(key);
  return translated && translated !== key ? translated : fallback;
}

function labelFor(t: LabelTranslate, channel: string, value: string): string {
  if (channel === 'framing') {
    return translateOrFallback(t, `styleSettings.framingLabel.${value}`, capitalize(value));
  }
  if (channel === 'lighting') {
    const lc = value.toLowerCase();
    for (const key of LIGHTING_KEYS) {
      if (lc.includes(key)) {
        return translateOrFallback(t, `styleSettings.lighting.${key}`, capitalize(value));
      }
    }
    return capitalize(value);
  }
  if (channel === 'weather') {
    return translateOrFallback(t, `styleSettings.weather.${value.toLowerCase()}`, capitalize(value));
  }
  if (channel === 'time_of_day') {
    return translateOrFallback(t, `styleSettings.timeOfDay.${value.toLowerCase()}`, capitalize(value));
  }
  if (channel === 'season') {
    return translateOrFallback(t, `styleSettings.season.${value.toLowerCase()}`, capitalize(value));
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

export default function StyleSettingsModal({ open, onClose, styleId, initialHints, onApply }: Props) {
  const app = useApp();
  const { t } = useTranslation('wizard');
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<StyleOptions | null>(null);
  const [hints, setHints] = useState<Record<string, any>>(() => ({ ...(initialHints ?? {}) }));

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
    // На открытие переинициализируем выбранные значения из последней
    // генерации (resolved_slots) — чтобы пользователь видел, какие
    // параметры реально применялись, и мог менять их относительно
    // текущего состояния, а не «с нуля».
    setHints({ ...(initialHints ?? {}) });
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
  // initialHints подхватываем только на момент открытия (open=true).
  // Если родитель пересчитает initialHints во время открытой модалки,
  // мы намеренно не перезаписываем uncommitted-выбор пользователя.
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
  // 1.31.1 — для curated-стилей показываем поле «Одежда» как только
  // канал в ``available_channels``, даже если ``clothing.allowed`` пустой.
  // У многих landmark-стилей (paris_eiffel, dubai_burj_khalifa) пул
  // намеренно пустой, чтобы не навязывать конкретные варианты, но
  // free-text input всё равно нужен — пользователь должен иметь
  // возможность задать одежду (особенно при season=winter, чтобы не
  // получить летнюю футболку посреди зимы).
  const hasClothing = isCurated
    ? curatedChannels.includes('clothing')
    : (options?.clothing?.length ?? 0) > 0;
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
        data-category={app.activeCategory}
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
                {t('styleSettings.title')}
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
              aria-label={t('styleSettings.close')}
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
                title={t('styleSettings.triggerTooltip')}
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
                    {t('styleSettings.triggerLabel')}
                  </span>
                  <span className="text-[13px] leading-[18px] text-text-primary truncate">
                    {triggerHeadline}
                  </span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] mt-[2px]">
                    {t('styleSettings.triggerHint')}
                  </span>
                </div>
              </div>
            )}

            {loading ? (
              <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-16)]">
                {t('styleSettings.loading')}
              </div>
            ) : !hasAnyField ? (
              <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-16)]">
                {t('styleSettings.noFields')}
              </div>
            ) : (
              <>
                {hasLighting && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {t('styleSettings.category.lighting')}
                    </span>
                    <Select
                      ariaLabel={t('styleSettings.category.lighting')}
                      value={hints.lighting ?? ''}
                      placeholder={t('styleSettings.auto')}
                      onChange={(v) => setHints((h) => ({ ...h, lighting: v }))}
                      options={[
                        { value: '', label: t('styleSettings.auto') },
                        ...options!.lighting!.map((opt) => ({
                          value: opt,
                          label: labelFor(t, 'lighting', opt),
                        })),
                      ]}
                    />
                  </div>
                )}

                {hasTimeOfDay && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {t('styleSettings.category.time_of_day')}
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
                        {t('styleSettings.auto')}
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
                            {labelFor(t, 'time_of_day', opt)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {hasSeason && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {t('styleSettings.category.season')}
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
                        {t('styleSettings.auto')}
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
                            {labelFor(t, 'season', opt)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {hasFraming && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {t('styleSettings.category.framing')}
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
                        title={t('styleSettings.defaultFramingTooltip')}
                      >
                        {t('styleSettings.default')}
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
                            {labelFor(t, 'framing', opt)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {hasScene && (
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
                      {t('styleSettings.category.scene')}
                    </span>
                    <input
                      type="text"
                      placeholder={t('styleSettings.scenePlaceholder')}
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
                      {t('styleSettings.category.clothing')}
                    </span>
                    <input
                      type="text"
                      placeholder={t('styleSettings.clothingPlaceholder')}
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
                      {t('styleSettings.category.weather')}
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
                        {t('styleSettings.auto')}
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
                            {labelFor(t, 'weather', opt)}
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
              {t('styleSettings.applyCta')}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}
