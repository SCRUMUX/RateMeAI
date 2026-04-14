import { useState, useRef } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from '@ai-ds/core/icons';
import { STYLES_BY_CATEGORY, type CategoryId } from '../../data/styles';
import CategoryTabs from '../CategoryTabs';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import { STYLES_PER_PAGE, PARAM_LABELS, computeStyleDeltas } from './shared';

interface Props {
  onNext: () => void;
}

export default function StepStyle({ onNext }: Props) {
  const app = useApp();
  const styleScrollRef = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(0);

  const activeTab = app.activeCategory;
  const styles = STYLES_BY_CATEGORY[activeTab];
  const hasStyles = styles.length > 0;
  const totalPages = Math.ceil(styles.length / STYLES_PER_PAGE);

  const clampedPage = Math.min(page, Math.max(totalPages - 1, 0));
  const pageStyles = styles.slice(clampedPage * STYLES_PER_PAGE, (clampedPage + 1) * STYLES_PER_PAGE);

  const PARAMS_BLOCK_ROWS = 5;
  const rightCount = Math.max(0, pageStyles.length - PARAMS_BLOCK_ROWS);
  const leftCount = pageStyles.length - rightCount;
  const leftCol = pageStyles.slice(0, leftCount);
  const rightCol = pageStyles.slice(leftCount);

  const allPages = Array.from({ length: totalPages }, (_, p) => {
    const start = p * STYLES_PER_PAGE;
    return styles.slice(start, start + STYLES_PER_PAGE);
  });

  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];
  const selectedIdx = selectedStyle ? styles.indexOf(selectedStyle) : -1;

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

  function handleTabChange(id: CategoryId) {
    app.setActiveCategory(id);
    app.setSelectedStyleKey('');
    setPage(0);
  }

  function handleStyleClick(key: string) {
    app.setSelectedStyleKey(key);
  }

  function handleStyleScroll() {
    const el = styleScrollRef.current;
    if (!el) return;
    const idx = Math.round(el.scrollLeft / el.offsetWidth);
    setPage(idx);
  }

  function handleSelectAndNext() {
    const effectiveStyle = app.selectedStyleKey || styles[0]?.key || '';
    if (!app.selectedStyleKey && effectiveStyle) {
      app.setSelectedStyleKey(effectiveStyle);
    }
    onNext();
  }

  const renderStyleRow = (s: typeof styles[number], gIdx: number) => (
    <div key={s.key}
      onClick={() => handleStyleClick(s.key)}
      className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all ${
        selectedIdx === gIdx ? 'glass-row-active' : 'glass-row'
      }`}
      style={{ '--gb-color': selectedIdx === gIdx ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)' : 'rgba(255, 255, 255, 0.10)' } as React.CSSProperties}
    >
      <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
      <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
        <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
      </div>
    </div>
  );

  const paramsBlock = (
    <div className="flex flex-col gap-[var(--space-12)]">
      {selectedStyle && (
        <div className="flex items-center gap-[var(--space-8)]">
          <span className="text-[20px]">{selectedStyle.icon}</span>
          <div className="flex flex-col min-w-0">
            <span className="text-[15px] leading-[22px] font-medium text-[#E6EEF8] truncate">{selectedStyle.name}</span>
            <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] truncate">{selectedStyle.desc}</span>
          </div>
        </div>
      )}

      <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-10)] rounded-[var(--radius-12)] p-[var(--space-12)]">
        {displayParams ? displayParams.map((p) => (
          <div key={p.key} className="flex flex-col gap-[var(--space-6)]">
            <div className="flex items-center justify-between">
              <span className="text-[13px] leading-[18px] text-[#E6EEF8]">{p.label}</span>
              <span className="flex items-center gap-[var(--space-6)] text-[13px] leading-[18px] tabular-nums">
                <span className="text-[var(--color-text-secondary)]">{p.value.toFixed(2)}</span>
                {p.delta > 0 && (
                  <span className="text-[var(--color-success-base)] text-[11px] font-medium">+{p.delta.toFixed(2)}</span>
                )}
                {p.delta < 0 && (
                  <span className="text-[var(--color-danger-base)] text-[11px] font-medium">{p.delta.toFixed(2)}</span>
                )}
              </span>
            </div>
            <div className="relative">
              <ProgressBar value={p.value} />
              {p.delta > 0 && (
                <div className="absolute inset-0"><ProgressBar value={Math.min(10, p.value + p.delta)} variant="success" /></div>
              )}
            </div>
          </div>
        )) : (
          <div className="text-[13px] text-[var(--color-text-muted)] text-center py-[var(--space-8)]">
            Загрузите фото для просмотра параметров
          </div>
        )}
      </div>

      <button
        onClick={handleSelectAndNext}
        disabled={!hasStyles}
        className="glass-btn-primary w-full py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] font-medium"
      >
        Генерировать
      </button>
    </div>
  );

  return (
    <div className="flex flex-col gap-[var(--space-16)] w-full max-w-[1000px] mx-auto">
      {/* Title */}
      <div className="flex flex-col items-center gap-[var(--space-6)] text-center">
        <h2 className="text-[24px] tablet:text-[28px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Выберите стиль
        </h2>
        <p className="text-[13px] tablet:text-[15px] leading-[18px] tablet:leading-[22px] text-[var(--color-text-secondary)] max-w-[420px]">
          Каждый стиль адаптирует образ под конкретный контекст и улучшает целевые метрики восприятия
        </p>
      </div>

      {/* Category tabs */}
      <CategoryTabs active={activeTab} onChange={handleTabChange} />

      {/* Placeholder for categories without styles */}
      {!hasStyles && (
        <div className="flex flex-col items-center justify-center py-10 gap-[var(--space-12)]">
          <span className="text-[40px]">🚧</span>
          <p className="text-[16px] leading-[24px] text-[var(--color-text-secondary)] font-medium">Скоро</p>
          <p className="text-[13px] leading-[18px] text-[var(--color-text-muted)] max-w-[280px] text-center">
            Стили для этой категории появятся в ближайшем обновлении
          </p>
        </div>
      )}

      {/* Styles section */}
      {hasStyles && (
        <>
          {/* Mobile: params block on top, then swipeable pages */}
          <div className="flex flex-col gap-[var(--space-12)] tablet:hidden">
            {paramsBlock}

            <div
              ref={styleScrollRef}
              onScroll={handleStyleScroll}
              className="flex flex-row w-full overflow-x-auto snap-x snap-mandatory scrollbar-hide"
            >
              {allPages.map((pageItems, pageIdx) => (
                <div key={pageIdx} className="w-full min-w-full snap-center flex flex-col gap-[var(--space-8)]">
                  {pageItems.map((s) => renderStyleRow(s, styles.indexOf(s)))}
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-[6px]">
                {allPages.map((_, i) => (
                  <button
                    key={i}
                    className={`w-2 h-2 rounded-full transition-colors ${clampedPage === i ? 'bg-[rgb(var(--accent-r),var(--accent-g),var(--accent-b))]' : 'bg-[rgba(255,255,255,0.25)]'}`}
                    onClick={() => {
                      const el = styleScrollRef.current;
                      if (el) el.scrollTo({ left: i * el.offsetWidth, behavior: 'smooth' });
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Tablet+: two-column layout with params block above right column */}
          <div className="hidden tablet:flex flex-row items-start gap-[var(--space-16)]">
            {/* Left column: styles */}
            <div className="flex-1 flex flex-col gap-[var(--space-8)]">
              {leftCol.map((s) => renderStyleRow(s, styles.indexOf(s)))}
            </div>

            {/* Right column: params block on top, then remaining styles */}
            <div className="flex-1 flex flex-col gap-[var(--space-12)]">
              {paramsBlock}
              {rightCol.length > 0 && (
                <div className="flex flex-col gap-[var(--space-8)]">
                  {rightCol.map((s) => renderStyleRow(s, styles.indexOf(s)))}
                </div>
              )}
            </div>
          </div>

          {/* Pagination (tablet+) */}
          {totalPages > 1 && (
            <div className="hidden tablet:flex items-center justify-center gap-[var(--space-12)]">
              <button
                onClick={() => setPage(Math.max(0, clampedPage - 1))}
                disabled={clampedPage === 0}
                className="glass-btn-ghost w-9 h-9 flex items-center justify-center rounded-[var(--radius-12)] text-[var(--color-text-muted)] hover:text-[#E6EEF8]"
              >
                <ChevronLeftIcon size={18} />
              </button>
              <span className="text-[13px] leading-[18px] text-[#E6EEF8] tabular-nums">
                {clampedPage + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, clampedPage + 1))}
                disabled={clampedPage === totalPages - 1}
                className="glass-btn-ghost w-9 h-9 flex items-center justify-center rounded-[var(--radius-12)] text-[var(--color-text-muted)] hover:text-[#E6EEF8]"
              >
                <ChevronRightIcon size={18} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
