import { useState, useRef } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from '@ai-ds/core/icons';
import { STYLES_BY_CATEGORY, getMockDelta, type CategoryId } from '../../data/styles';
import CategoryTabs from '../CategoryTabs';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import { STYLES_PER_PAGE } from './shared';

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
  const predictedDelta = (selectedStyle.deltaRange[0] + selectedStyle.deltaRange[1]) / 2;
  const predictedAfterScore = +(beforeScore + predictedDelta).toFixed(2);

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
      <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
        {getMockDelta(s.deltaRange, s.key)}
      </span>
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

      {/* Category tabs */}
      <div className="flex items-center justify-center w-full">
        <CategoryTabs active={activeTab} onChange={handleTabChange} />
      </div>

      <div className="flex flex-col tablet:flex-row gap-[var(--space-24)] tablet:gap-[var(--space-32)]">
        {/* Style list */}
        <div className="flex-1 min-w-0">
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

        {/* Preview card */}
        <div className="w-full tablet:w-[240px] shrink-0">
          <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-16)] flex flex-col gap-[var(--space-12)]">
            <div className="flex items-center gap-[var(--space-8)]">
              <span className="text-[20px]">{selectedStyle.icon}</span>
              <div className="flex flex-col min-w-0">
                <span className="text-[15px] leading-[22px] font-medium text-[#E6EEF8] truncate">{selectedStyle.name}</span>
                <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] truncate">{selectedStyle.desc}</span>
              </div>
            </div>

            <div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />

            <div className="flex flex-col gap-[var(--space-8)]">
              <div className="flex items-center justify-between">
                <span className="text-[13px] leading-[18px] text-[var(--color-text-muted)]">Текущий скор</span>
                <span className="text-[13px] leading-[18px] text-[var(--color-text-secondary)] tabular-nums">{beforeScore.toFixed(2)}</span>
              </div>
              <ProgressBar value={beforeScore} />
              <div className="flex items-center justify-between">
                <span className="text-[13px] leading-[18px] text-[var(--color-text-muted)]">Прогноз</span>
                <span className="text-[13px] leading-[18px] text-[var(--color-brand-primary)] font-semibold tabular-nums">~{predictedAfterScore.toFixed(2)}</span>
              </div>
              <ProgressBar value={predictedAfterScore} accent />
            </div>

            <button
              onClick={handleSelectAndNext}
              className="glass-btn-primary w-full py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] font-medium mt-[var(--space-4)]"
            >
              Генерировать
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
