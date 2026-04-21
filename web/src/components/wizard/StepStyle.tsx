import { useMemo, useState } from 'react';
import { COMING_SOON_CATEGORIES, getMockDelta } from '../../data/styles';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import StylesSheet from './StylesSheet';
import { computeLockedKeys, getUserLockSeed, UNLOCK_AFTER_GENERATIONS } from './lockedStyles';
import { PARAM_LABELS, computeStyleDeltas } from './shared';

interface Props {
  onNext: () => void;
}

export default function StepStyle({ onNext }: Props) {
  const app = useApp();
  const activeTab = app.activeCategory;
  const styles = app.effectiveStyleList;
  const hasStyles = styles.length > 0;
  const isComingSoon = COMING_SOON_CATEGORIES.includes(activeTab);

  const [sheetOpen, setSheetOpen] = useState(false);

  const userSeed = useMemo(
    () => getUserLockSeed(app.session?.userId ?? null),
    [app.session?.userId],
  );
  const lockedKeys = useMemo(
    () => computeLockedKeys(styles, userSeed, app.taskHistoryCount),
    [styles, userSeed, app.taskHistoryCount],
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
        <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] font-medium">Скоро...</p>
        <p className="text-[12px] leading-[16px] text-[var(--color-text-muted)] text-center max-w-[260px]">
          Генерация для этого направления появится в ближайшем обновлении
        </p>
      </div>
      <button disabled className="glass-btn-primary w-full py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] font-medium opacity-40 cursor-not-allowed">
        Генерировать
      </button>
    </div>
  );

  return (
    <div className="flex flex-col tablet:h-full w-full max-w-[520px] tablet:max-w-[960px] mx-auto">
      <div className="shrink-0 flex flex-col items-center gap-[var(--space-4)] text-center pb-[var(--space-12)]">
        <h2 className="text-[20px] tablet:text-[22px] leading-[1.2] font-semibold text-[#E6EEF8]">Выберите стиль</h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          Каждый стиль улучшает метрики восприятия под конкретный контекст
        </p>
      </div>

      {isComingSoon ? (
        comingSoonBlock
      ) : hasStyles ? (
        <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] tablet:gap-[var(--space-20)] tablet:flex-1 tablet:min-h-0">
          {/* Left column — selected + parameters */}
          <div className="flex flex-col gap-[var(--space-12)] w-full tablet:flex-1 tablet:min-w-0">
            {/* 1. Selected style — recap */}
            {selectedStyle && (
              <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-12)] tablet:p-[var(--space-16)] flex flex-col gap-[var(--space-6)]">
                <div className="flex items-center gap-[var(--space-10)]">
                  <span className="text-[24px] tablet:text-[28px] leading-none">{selectedStyle.icon}</span>
                  <div className="flex flex-col min-w-0">
                    <span className="text-[15px] tablet:text-[16px] leading-[20px] tablet:leading-[22px] font-semibold text-[#E6EEF8] truncate">{selectedStyle.name}</span>
                    <span className="text-[11px] tablet:text-[12px] leading-[14px] tablet:leading-[16px] text-[var(--color-text-muted)] truncate">Выбранный стиль</span>
                  </div>
                </div>
                <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)]">
                  {selectedStyle.desc}
                </p>
              </div>
            )}

            {/* 2. Parameters block */}
            <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-10)] rounded-[var(--radius-12)] p-[var(--space-12)]">
              {displayParams ? displayParams.map((p) => (
                <div key={p.key} className="flex flex-col gap-[var(--space-4)]">
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[#E6EEF8]">{p.label}</span>
                    <span className="flex items-center gap-[var(--space-6)] text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] tabular-nums">
                      <span className="text-[var(--color-text-secondary)]">{p.value.toFixed(2)}</span>
                      {p.delta > 0 && <span className="text-[var(--color-success-base)] text-[11px] font-medium">+{p.delta.toFixed(2)}</span>}
                      {p.delta < 0 && <span className="text-[var(--color-danger-base)] text-[11px] font-medium">{p.delta.toFixed(2)}</span>}
                    </span>
                  </div>
                  <ProgressBar value={p.value} accent delta={p.delta} />
                </div>
              )) : (
                <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-8)]">
                  Загрузите фото для просмотра параметров
                </div>
              )}
            </div>
          </div>

          {/* Right column — recommended + CTAs */}
          <div className="flex flex-col gap-[var(--space-10)] w-full tablet:w-[320px] tablet:shrink-0">
            {/* 3. Recommended styles */}
            {recommendedStyles.length > 0 && (
              <div className="flex flex-col gap-[var(--space-6)]">
                <span className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] font-medium text-[var(--color-text-muted)]">Рекомендуемые стили</span>
                {recommendedStyles.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => handlePickStyle(s.key)}
                    className="gradient-border-item flex items-center w-full px-[var(--space-12)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[40px] cursor-pointer rounded-[var(--radius-12)] transition-all glass-row text-left"
                    style={{ '--gb-color': 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.15)' } as React.CSSProperties}
                  >
                    <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
                    <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                      <span className="text-[14px] leading-[18px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
                    </div>
                    <span className="px-[var(--space-6)] py-[var(--space-2)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                      {getMockDelta(s.deltaRange, s.key)}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* 4. Bottom-sheet trigger */}
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium text-[#E6EEF8] inline-flex items-center justify-center gap-[var(--space-6)]"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M3 5h10M3 8h10M3 11h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Хочу другой образ
              {app.taskHistoryCount < UNLOCK_AFTER_GENERATIONS && (
                <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">
                  · {styles.length} стилей
                </span>
              )}
            </button>

            {/* 5. Primary CTA — pinned bottom on desktop */}
            <button
              onClick={handleGenerate}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium tablet:mt-auto"
            >
              Генерировать
            </button>
          </div>
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
