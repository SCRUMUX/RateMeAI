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
  const totalPages = Math.ceil(styles.length / STYLES_PER_PAGE);

  const clampedPage = Math.min(page, totalPages - 1);
  const pageStyles = styles.slice(clampedPage * STYLES_PER_PAGE, (clampedPage + 1) * STYLES_PER_PAGE);
  const half = Math.ceil(pageStyles.length / 2);
  const leftCol = pageStyles.slice(0, half);
  const rightCol = pageStyles.slice(half);

  const allPages = Array.from({ length: totalPages }, (_, p) => {
    const start = p * STYLES_PER_PAGE;
    return styles.slice(start, start + STYLES_PER_PAGE);
  });

  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];
  const selectedIdx = styles.indexOf(selectedStyle);

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : 5.99;
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

  return (
    <div className="flex flex-col gap-[var(--space-24)] w-full max-w-[1000px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
        <h2 className="text-[24px] tablet:text-[32px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Выберите стиль
        </h2>
        <p className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] max-w-[440px]">
          Каждый стиль адаптирует образ под конкретный контекст и улучшает целевые метрики восприятия
        </p>
      </div>

      {/* Top section: photo + category (left) | params + generate (right) */}
      <div className="flex flex-col tablet:flex-row gap-[var(--space-24)] tablet:gap-[var(--space-32)]">
        {/* Left: photo card + category tabs */}
        <div className="flex flex-col gap-[var(--space-16)] w-full tablet:w-[260px] shrink-0">
          <div className="gradient-border-card glass-card flex flex-col rounded-[var(--radius-12)] overflow-hidden">
            <div className="w-full aspect-[3/4] tablet:h-[280px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
              {app.photo ? (
                <img src={app.photo.preview} alt="Original" className="w-full h-full object-cover" />
              ) : (
                <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
              )}
            </div>
            <div className="flex flex-col gap-[var(--space-8)] p-[var(--space-12)]">
              <div className="flex items-center justify-between">
                <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">Исходное</span>
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] tabular-nums">{beforeScore.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              </div>
              <ProgressBar value={beforeScore} />
            </div>
          </div>
          <div className="flex items-center justify-center w-full">
            <CategoryTabs active={activeTab} onChange={handleTabChange} />
          </div>
        </div>

        {/* Right: params with deltas + generate button */}
        <div className="flex-1 flex flex-col gap-[var(--space-16)]">
          {/* Selected style header */}
          <div className="flex items-center gap-[var(--space-8)]">
            <span className="text-[20px]">{selectedStyle.icon}</span>
            <div className="flex flex-col min-w-0">
              <span className="text-[15px] leading-[22px] font-medium text-[#E6EEF8] truncate">{selectedStyle.name}</span>
              <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] truncate">{selectedStyle.desc}</span>
            </div>
          </div>

          {/* Perception parameters with style deltas */}
          <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
            {displayParams ? displayParams.map((p) => (
              <div key={p.key} className="flex flex-col gap-[var(--space-8)]">
                <div className="flex items-center justify-between">
                  <span className="text-[14px] leading-[20px] text-[#E6EEF8]">{p.label}</span>
                  <span className="flex items-center gap-[var(--space-8)] text-[14px] leading-[20px] tabular-nums">
                    <span className="text-[var(--color-text-secondary)]">{p.value.toFixed(2)}</span>
                    {p.delta > 0 && (
                      <span className="text-[var(--color-success-base)] text-[12px] font-medium">+{p.delta.toFixed(2)}</span>
                    )}
                    {p.delta < 0 && (
                      <span className="text-[var(--color-danger-base)] text-[12px] font-medium">{p.delta.toFixed(2)}</span>
                    )}
                  </span>
                </div>
                <div className="relative">
                  <ProgressBar value={p.value} />
                  {p.delta > 0 && (
                    <div className="absolute inset-0"><ProgressBar value={Math.min(10, p.value + p.delta)} accent /></div>
                  )}
                </div>
              </div>
            )) : (
              <div className="text-[14px] text-[var(--color-text-muted)] text-center py-[var(--space-12)]">
                Загрузите фото для просмотра параметров
              </div>
            )}
          </div>

          <button
            onClick={handleSelectAndNext}
            className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
          >
            Генерировать
          </button>
        </div>
      </div>

      {/* Bottom section: style list (full width) */}
      <div className="w-full">
        {/* Mobile: swipeable pages */}
        <div
          ref={styleScrollRef}
          onScroll={handleStyleScroll}
          className="flex tablet:hidden flex-row overflow-x-auto snap-x snap-mandatory scrollbar-hide"
        >
          {allPages.map((pageItems, pageIdx) => (
            <div key={pageIdx} className="w-full min-w-full snap-center flex flex-col gap-[var(--space-12)]">
              {pageItems.map((s) => renderStyleRow(s, styles.indexOf(s)))}
            </div>
          ))}
        </div>

        {/* Mobile: page indicators */}
        {totalPages > 1 && (
          <div className="flex tablet:hidden items-center justify-center gap-[6px] mt-[var(--space-8)]">
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

        {/* Tablet+: two-column layout */}
        <div className="hidden tablet:flex flex-row gap-[var(--space-16)]">
          <div className="flex-1 flex flex-col gap-[var(--space-12)]">
            {leftCol.map((s) => renderStyleRow(s, styles.indexOf(s)))}
          </div>
          <div className="flex-1 flex flex-col gap-[var(--space-12)]">
            {rightCol.map((s) => renderStyleRow(s, styles.indexOf(s)))}
          </div>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="hidden tablet:flex items-center justify-center gap-[var(--space-12)] mt-[var(--space-16)]">
            <button
              onClick={() => setPage(Math.max(0, clampedPage - 1))}
              disabled={clampedPage === 0}
              className="glass-btn-ghost w-10 h-10 flex items-center justify-center rounded-[var(--radius-12)] text-[var(--color-text-muted)] hover:text-[#E6EEF8]"
            >
              <ChevronLeftIcon size={20} />
            </button>
            <span className="text-[14px] leading-[20px] text-[#E6EEF8] tabular-nums">
              {clampedPage + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, clampedPage + 1))}
              disabled={clampedPage === totalPages - 1}
              className="glass-btn-ghost w-10 h-10 flex items-center justify-center rounded-[var(--radius-12)] text-[var(--color-text-muted)] hover:text-[#E6EEF8]"
            >
              <ChevronRightIcon size={20} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
