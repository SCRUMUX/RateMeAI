import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { COMING_SOON_CATEGORIES, getMockDelta } from '../../data/styles';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import StylesSheet from './StylesSheet';
import {
  computeCompositionLockedKeys,
  computeCompositionRiskyKeys,
  computeLockedKeys,
} from './lockedStyles';
import { PARAM_LABELS, computeStyleDeltas } from './shared';

interface Props {
  onNext: () => void;
}

export default function StepStyle({ onNext }: Props) {
  const app = useApp();
  const { t } = useTranslation('wizard');
  const FRAMING_OPTIONS = [
    { id: 'portrait', label: t('style.framingPortrait') },
    { id: 'half_body', label: t('style.framingHalf') },
    { id: 'full_body', label: t('style.framingFull') },
  ];
  const activeTab = app.activeCategory;
  const styles = app.effectiveStyleList;
  const hasStyles = styles.length > 0;
  const isComingSoon = COMING_SOON_CATEGORIES.includes(activeTab);

  const [sheetOpen, setSheetOpen] = useState(false);

  // Composition Safety Layer locks merge with the unlock-by-generations
  // set so the picker treats both blockers identically. Risky styles
  // (CSL soft warnings) are tracked separately because the user can
  // still pick them — we only show a notice.
  const lockedKeys = useMemo(() => {
    const unlockLocked = computeLockedKeys(styles, app.taskHistoryCount);
    const cslLocked = computeCompositionLockedKeys(styles, app.compositionClass);
    return new Set<string>([...unlockLocked, ...cslLocked]);
  }, [styles, app.taskHistoryCount, app.compositionClass]);
  const riskyKeys = useMemo(
    () => computeCompositionRiskyKeys(styles, app.compositionClass),
    [styles, app.compositionClass],
  );

  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];

  const hasRealScores = !!app.preAnalysis;
  const beforePerception = hasRealScores ? app.preAnalysis!.perception_scores : null;
  const styleDelta = selectedStyle ? computeStyleDeltas(selectedStyle, activeTab) : null;

  const displayParams = beforePerception
    ? Object.entries(beforePerception)
        .filter(([k]) => k !== 'authenticity')
        .map(([k, v]) => ({
          key: k,
          label: PARAM_LABELS[k] ?? k,
          value: v as number,
          delta: styleDelta?.[k] ?? 0,
        }))
    : null;

  const recommendedStyles = useMemo(() => {
    if (!displayParams || displayParams.length === 0) return [];
    const weakest = displayParams.reduce((min, p) => p.value < min.value ? p : min, displayParams[0]);
    return styles
      .filter(s => s.param === weakest.key && !lockedKeys.has(s.key) && s.key !== selectedStyle?.key)
      .sort((a, b) => (b.deltaRange[0] + b.deltaRange[1]) - (a.deltaRange[0] + a.deltaRange[1]))
      .slice(0, 2);
  }, [displayParams, styles, lockedKeys, selectedStyle?.key]);

  function handlePickStyle(key: string) {
    if (isComingSoon) return;
    if (lockedKeys.has(key)) return;
    app.setSelectedStyleKey(key);
  }

  function handleGenerate() {
    if (isComingSoon) return;
    const effectiveStyle = app.selectedStyleKey || styles[0]?.key || '';
    if (!app.selectedStyleKey && effectiveStyle) {
      app.setSelectedStyleKey(effectiveStyle);
    }
    onNext();
  }

  const comingSoonBlock = (
    <div className="flex flex-col gap-[var(--space-12)]">
      <div className="gradient-border-card glass-card flex flex-col items-center justify-center gap-[var(--space-8)] rounded-[var(--radius-12)] p-[var(--space-16)] min-h-[120px]">
        <span className="text-[32px]">🚧</span>
        <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] font-medium">{t('style.comingSoon')}</p>
        <p className="text-[12px] leading-[16px] text-[var(--color-text-muted)] text-center max-w-[260px]">
          {t('style.comingSoonDesc')}
        </p>
      </div>
      <button disabled className="glass-btn-primary w-full py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] font-medium opacity-40 cursor-not-allowed">
        {t('style.generateCta')}
      </button>
    </div>
  );

  return (
    <div className="flex flex-col w-full max-w-[520px] mx-auto gap-[var(--space-24)]">
      <div className="flex flex-col items-center gap-[var(--space-4)] text-center">
        <h2 className="text-[20px] tablet:text-[24px] leading-[1.2] font-semibold text-[var(--color-text-primary)]">{t('style.title')}</h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          {t('style.subtitle')}
        </p>
      </div>

      {/* Composition Safety Layer — informational banner. Shown only
          when the upload sits in one of the constrained categories so
          users understand why some framings / styles are locked. */}
      {!isComingSoon && (app.compositionClass === 'face_closeup' || app.compositionClass === 'unknown') && (
        <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-12)] flex items-start gap-[var(--space-8)] text-[12px] leading-[16px] text-[var(--color-text-secondary)]">
          <span aria-hidden className="text-[16px] leading-none">💡</span>
          <span>
            {app.compositionClass === 'unknown'
              ? t('style.compositionUnknown')
              : t('style.compositionFaceCloseup')}
          </span>
        </div>
      )}

      {/* CSL warning when the *currently selected* style is risky for
          the upload (soft warn, not a block). Keeps the user moving
          but flags the trade-off before they tap Generate. */}
      {!isComingSoon && selectedStyle && riskyKeys.has(selectedStyle.key) && (
        <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-12)] flex items-start gap-[var(--space-8)] text-[12px] leading-[16px] text-[var(--color-warning-base)]">
          <span aria-hidden className="text-[16px] leading-none">⚠️</span>
          <span>{t('style.styleRiskyComposition')}</span>
        </div>
      )}

      {isComingSoon ? (
        comingSoonBlock
      ) : hasStyles ? (
        <div className="flex flex-col gap-[var(--space-24)]">
          {/* 1. Selected style — recap + future long description slot */}
          {selectedStyle && (
            <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-16)] flex flex-col gap-[var(--space-12)]">
              <div className="flex items-center gap-[var(--space-10)]">
                <span className="text-[28px] leading-none">{selectedStyle.icon}</span>
                <div className="flex flex-col min-w-0">
                  <span className="text-[16px] leading-[22px] font-semibold text-[var(--color-text-primary)] truncate">{selectedStyle.name}</span>
                  <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] truncate">{t('style.selectedTag')}</span>
                </div>
              </div>
              <p className="text-[13px] leading-[18px] text-[var(--color-text-secondary)]">
                {selectedStyle.desc}
              </p>
              
              {/* Framing selector — Composition Safety Layer gates the
                  options here based on the pre-analyze composition_class.
                  Disabled buttons keep their slot in the row (we don't
                  hide them outright) so users see what they unlock by
                  reuploading a wider crop. */}
              <div className="flex flex-col gap-[var(--space-8)] pt-[var(--space-4)] border-t border-[var(--glass-border-soft)]">
                <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)]">{t('style.framingTitle')}</span>
                <div className="flex bg-[var(--glass-surface-soft)] p-1 rounded-[var(--radius-8)]">
                  {FRAMING_OPTIONS.map((opt) => {
                    const allowed = app.allowedFramings.includes(opt.id);
                    const lockReason = app.compositionClass === 'unknown'
                      ? t('style.framingLockedUnknown')
                      : t('style.framingLocked');
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        disabled={!allowed}
                        title={!allowed ? lockReason : undefined}
                        onClick={() => allowed && app.setFraming(opt.id)}
                        className={`flex-1 py-[var(--space-6)] text-[13px] leading-[18px] font-medium rounded-[var(--radius-6)] transition-all ${
                          app.framing === opt.id
                            ? 'bg-[var(--color-surface-2)] text-[var(--color-text-primary)] shadow-sm'
                            : allowed
                              ? 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                              : 'text-[var(--color-text-muted)] opacity-40 cursor-not-allowed'
                        }`}
                      >
                        {opt.label}
                        {!allowed && <span aria-hidden className="ml-[2px]">🔒</span>}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* 2. Parameters block */}
          <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
            {displayParams ? displayParams.map((p) => (
              <div key={p.key} className="flex flex-col gap-[var(--space-6)]">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] leading-[18px] text-[var(--color-text-primary)]">{p.label}</span>
                  <span className="flex items-center gap-[var(--space-6)] text-[13px] leading-[18px] tabular-nums">
                    <span className="text-[var(--color-text-secondary)]">{p.value.toFixed(2)}</span>
                    {p.delta > 0 && <span className="text-[var(--color-success-base)] text-[11px] font-medium">+{p.delta.toFixed(2)}</span>}
                    {p.delta < 0 && <span className="text-[var(--color-danger-base)] text-[11px] font-medium">{p.delta.toFixed(2)}</span>}
                  </span>
                </div>
                <ProgressBar value={p.value} accent delta={p.delta} />
              </div>
            )) : (
              <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-8)]">
                {t('style.noPhotoForParams')}
              </div>
            )}
          </div>

          {/* 3. Recommended styles */}
          {recommendedStyles.length > 0 && (
            <div className="flex flex-col gap-[var(--space-8)]">
              <span className="text-[13px] leading-[18px] font-medium text-[var(--color-text-muted)]">{t('style.recommended')}</span>
              {recommendedStyles.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => handlePickStyle(s.key)}
                  className="gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[44px] cursor-pointer rounded-[var(--radius-12)] transition-all glass-row text-left"
                  style={{ '--gb-color': 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.15)' } as React.CSSProperties}
                >
                  <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
                  <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                    <span className="text-[15px] leading-[20px] text-[var(--color-text-primary)] font-medium truncate">{s.name}</span>
                    <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
                  </div>
                  <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[13px] leading-[18px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                    {getMockDelta(s.deltaRange, s.key)}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* 4. Primary CTA */}
          <button
            onClick={handleGenerate}
            className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
          >
            {t('style.generateCta')}
          </button>

          {/* 5. Bottom-sheet trigger */}
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium text-[var(--color-text-primary)] inline-flex items-center justify-center gap-[var(--space-6)]"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M3 5h10M3 8h10M3 11h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {t('style.anotherLook')}
            {styles.length - lockedKeys.size > 0 && (
              <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">
                {t('style.anotherLookCount', { count: styles.length - lockedKeys.size })}
              </span>
            )}
          </button>
        </div>
      ) : null}

      <StylesSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        styles={styles}
        selectedKey={app.selectedStyleKey}
        lockedKeys={lockedKeys}
        onPick={handlePickStyle}
      />
    </div>
  );
}
