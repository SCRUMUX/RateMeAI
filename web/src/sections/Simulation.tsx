import { useState } from 'react';
import { STYLES_BY_CATEGORY, getMockDelta, type CategoryId } from '../data/styles';
import { getTestimonialsByCategory } from '../data/testimonials';
import CategoryTabs from '../components/CategoryTabs';
import ReviewModal from '../components/ReviewModal';
import { useApp } from '../context/AppContext';

const ITEMS_PER_PAGE = 5;

export default function Simulation() {
  const { activeCategory, setActiveCategory } = useApp();
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalIdx, setModalIdx] = useState(0);

  const testimonials = getTestimonialsByCategory(activeCategory);
  const styles = STYLES_BY_CATEGORY[activeCategory];

  const testimonialsWithStyle = testimonials.map(t => ({
    ...t,
    style: styles.find(s => s.key === t.styleKey) ?? styles[0],
  }));

  const visible = testimonialsWithStyle.slice(0, ITEMS_PER_PAGE);
  const remaining = styles.length - ITEMS_PER_PAGE;
  const selected = visible[selectedIdx] ?? visible[0];

  function handleCategoryChange(id: CategoryId) {
    setActiveCategory(id);
    setSelectedIdx(0);
  }

  function openModal() {
    setModalIdx(selectedIdx);
    setModalOpen(true);
  }

  return (
    <section id="стили" className="relative z-[2] flex flex-col items-center gap-[var(--space-96)] px-[var(--space-24)] py-[120px]"
      style={{ minHeight: '100vh' }}
    >
      {/* Heading */}
      <div className="relative flex flex-col items-center gap-[var(--space-12)] text-center">
        <h2 className="text-[64px] font-semibold leading-[1] text-[#E6EEF8]">
          3 категории
        </h2>
        <h2 className="text-[64px] font-semibold leading-[1]"
          style={{
            background: 'linear-gradient(103deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          — под любую задачу
        </h2>
        <p className="text-[20px] leading-[28px] text-[var(--color-text-secondary)] max-w-[696px]">
          В каждой категории — более 100 уникальных стилей.
          Каждая генерация улучшает психологию восприятия
        </p>
        <p className="text-[18px] leading-[28px] text-[var(--color-text-secondary)] max-w-[660px]">
          Каждый стиль генерирует новое фото и улучшает психологию
          восприятия для конкретной жизненной ситуации
        </p>
      </div>

      {/* Category tabs */}
      <div className="relative flex items-center justify-center">
        <CategoryTabs active={activeCategory} onChange={handleCategoryChange} />
      </div>

      {/* Content: style list + photos */}
      <div className="relative flex items-start justify-between w-full max-w-[1200px] gap-[70px]">
        {/* Style list */}
        <div className="flex flex-col gap-[var(--space-12)] flex-1 max-w-[588px]">
          {visible.map((t, i) => (
            <div key={t.id}
              onClick={() => setSelectedIdx(i)}
              className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all ${
                selectedIdx === i
                  ? 'glass-row-active'
                  : 'glass-row'
              }`}
              style={{ '--gb-color': selectedIdx === i ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)' : 'rgba(255, 255, 255, 0.10)' } as React.CSSProperties}
            >
              <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">
                {t.style.icon}
              </div>
              <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium truncate">
                  {t.style.name}
                </span>
                <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">
                  {t.style.desc}
                </span>
              </div>
              <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                {getMockDelta(t.deltaRange, t.style.key)}
              </span>
            </div>
          ))}

          {remaining > 0 && (
            <button className="glass-btn-secondary flex items-center justify-center w-full mt-[var(--space-12)] px-[var(--space-20)] py-[var(--space-10)] rounded-[var(--radius-12)] text-[var(--color-brand-primary)] text-[16px] leading-[24px] font-medium">
              Ещё {remaining} образов
            </button>
          )}
        </div>

        {/* Photo cards -- fixed height */}
        <div
          className="flex items-start gap-[70px] cursor-pointer group"
          onClick={openModal}
        >
          {/* Original photo */}
          <div className="gradient-border-card glass-card flex flex-col w-[236px] h-[440px] rounded-[var(--radius-12)] overflow-hidden transition-transform group-hover:scale-[1.02]">
            <div className="w-[236px] h-[315px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
              <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
            </div>
            <div className="flex flex-col justify-between flex-1 pt-[var(--space-12)] pb-[var(--space-16)] px-[var(--space-12)]">
              <div className="flex flex-col gap-[var(--space-8)]">
                <div className="flex items-center justify-between">
                  <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">Исходное</span>
                  <span className="flex items-center gap-1">
                    <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">{selected.beforeScore.toFixed(2)}</span>
                    <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                  </span>
                </div>
                <div className="h-1.5 rounded-full glass-progress-track overflow-hidden">
                  <div className="h-full rounded-full glass-progress-fill-muted" style={{ width: `${(selected.beforeScore / 10) * 100}%` }} />
                </div>
              </div>
              <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)] truncate">
                {selected.nickname}
              </span>
            </div>
          </div>

          {/* Generated photo */}
          <div className="gradient-border-card glass-card flex flex-col w-[236px] h-[440px] rounded-[var(--radius-12)] overflow-hidden transition-transform group-hover:scale-[1.02]">
            <div className="w-[236px] h-[315px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
              <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50" />
            </div>
            <div className="flex flex-col justify-between flex-1 pt-[var(--space-12)] pb-[var(--space-16)] px-[var(--space-12)]">
              <div className="flex flex-col gap-[var(--space-8)]">
                <div className="flex items-center justify-between">
                  <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">{selected.style.name}</span>
                  <span className="flex items-center gap-1">
                    <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">{selected.afterScore.toFixed(2)}</span>
                    <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                  </span>
                </div>
                <div className="h-1.5 rounded-full glass-progress-track overflow-hidden">
                  <div className="h-full rounded-full glass-progress-fill" style={{ width: `${(selected.afterScore / 10) * 100}%` }} />
                </div>
              </div>
              <p className="text-[13px] leading-[18px] italic text-[var(--color-text-secondary)] line-clamp-2">
                &laquo;{selected.shortReview}&raquo;
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Review modal / slider */}
      <ReviewModal
        testimonials={testimonials}
        initialIndex={modalIdx}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
      />
    </section>
  );
}
