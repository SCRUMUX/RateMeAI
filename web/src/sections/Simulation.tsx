import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CATEGORIES, STYLES_BY_CATEGORY, getMockDelta, type CategoryId } from '../data/styles';
import { getTestimonialsByCategory } from '../data/testimonials';
import CategoryTabs from '../components/CategoryTabs';
import ReviewModal from '../components/ReviewModal';
import { useApp } from '../context/AppContext';

const ITEMS_PER_PAGE = 5;
const COMING_SOON_CATEGORIES: CategoryId[] = ['model', 'brand', 'memes'];

export default function Simulation() {
  const { activeCategory, setActiveCategory } = useApp();
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalIdx, setModalIdx] = useState(0);

  const isComingSoon = COMING_SOON_CATEGORIES.includes(activeCategory);
  const testimonials = getTestimonialsByCategory(activeCategory);
  const styles = STYLES_BY_CATEGORY[activeCategory];

  const testimonialsWithStyle = testimonials.map(t => ({
    ...t,
    style: styles.find(s => s.key === t.styleKey) ?? styles[0],
  }));

  const visible = testimonialsWithStyle.slice(0, ITEMS_PER_PAGE);
  const remaining = styles.length - ITEMS_PER_PAGE;
  const selected = visible[selectedIdx] ?? visible[0];
  const categoryLabel = CATEGORIES.find(c => c.id === activeCategory)?.label ?? activeCategory;

  function handleCategoryChange(id: CategoryId) {
    setActiveCategory(id);
    setSelectedIdx(0);
  }

  function openModal() {
    setModalIdx(selectedIdx);
    setModalOpen(true);
  }

  return (
    <section id="стили" className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-96)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[120px]"
      style={{ minHeight: '100vh' }}
    >
      {/* Heading */}
      <div className="relative flex flex-col items-center gap-[var(--space-12)] text-center">
        <h2 className="text-[32px] tablet:text-[48px] desktop:text-[64px] font-semibold leading-[1] text-[#E6EEF8]">
          6 категорий
        </h2>
        <h2 className="text-[32px] tablet:text-[48px] desktop:text-[64px] font-semibold leading-[1]"
          style={{
            background: 'linear-gradient(103deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          — под любую задачу
        </h2>
        <p className="text-[16px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] text-[var(--color-text-secondary)] max-w-[696px]">
          В каждой категории — более 100 уникальных стилей.
          Каждая генерация улучшает психологию восприятия
        </p>
        <p className="text-[15px] tablet:text-[18px] leading-[22px] tablet:leading-[28px] text-[var(--color-text-secondary)] max-w-[660px]">
          Каждый стиль генерирует новое фото и улучшает психологию
          восприятия для конкретной жизненной ситуации
        </p>
      </div>

      {/* Category tabs */}
      <div className="relative flex items-center justify-center w-full">
        <CategoryTabs active={activeCategory} onChange={handleCategoryChange} />
      </div>

      {/* Coming soon placeholder for new categories */}
      {isComingSoon && (
        <div className="flex flex-col items-center gap-[var(--space-24)] w-full max-w-[600px] py-[var(--space-32)]">
          <div className="gradient-border-card glass-card flex flex-col items-center justify-center gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-32)] w-full">
            <span className="text-[48px]">🚧</span>
            <h3 className="text-[24px] tablet:text-[32px] font-semibold text-[#E6EEF8]">{categoryLabel}</h3>
            <p className="text-[16px] leading-[24px] text-[var(--color-text-secondary)] text-center max-w-[400px]">
              Генерация для этого направления появится в ближайшем обновлении. Следите за новостями!
            </p>
            <Link
              to="/app"
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[22px] rounded-[var(--radius-pill)] font-medium no-underline mt-[var(--space-8)]"
            >
              Попробовать другие стили
            </Link>
          </div>
        </div>
      )}

      {/* Content: style list + photos (only for categories with testimonials) */}
      {!isComingSoon && selected && (
        <div className="relative flex flex-col desktop:flex-row items-stretch desktop:items-start desktop:justify-between w-full max-w-[1200px] gap-[var(--space-24)] desktop:gap-[70px]">
          {/* Style list */}
          <div className="flex flex-col gap-[var(--space-12)] w-full desktop:flex-1 desktop:max-w-[588px] order-last desktop:order-first">
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
              <Link to="/app" className="glass-btn-secondary flex items-center justify-center w-full mt-[var(--space-12)] px-[var(--space-20)] py-[var(--space-10)] rounded-[var(--radius-12)] text-[var(--color-brand-primary)] text-[16px] leading-[24px] font-medium no-underline">
                Ещё {remaining} образов
              </Link>
            )}
          </div>

          {/* Photo cards */}
          <div
            className="flex flex-row items-start gap-[var(--space-16)] tablet:gap-[70px] cursor-pointer group justify-center order-first desktop:order-last"
            onClick={openModal}
          >
            {/* Original photo */}
            <div className="gradient-border-card glass-card flex flex-col w-[calc(50%-var(--space-8))] tablet:w-[236px] rounded-[var(--radius-12)] overflow-hidden transition-transform group-hover:scale-[1.02]">
              <div className="w-full aspect-[3/4] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
                <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
              </div>
              <div className="flex flex-col justify-between flex-1 pt-[var(--space-12)] pb-[var(--space-16)] px-[var(--space-12)]">
                <div className="flex flex-col gap-[var(--space-8)]">
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[#E6EEF8] font-medium">Исходное</span>
                    <span className="flex items-center gap-1">
                      <span className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-secondary)]">{selected.beforeScore.toFixed(2)}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full glass-progress-track overflow-hidden">
                    <div className="h-full rounded-full glass-progress-fill-muted" style={{ width: `${(selected.beforeScore / 10) * 100}%` }} />
                  </div>
                </div>
                <span className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-muted)] truncate mt-[var(--space-8)]">
                  {selected.nickname}
                </span>
              </div>
            </div>

            {/* Generated photo */}
            <div className="gradient-border-card glass-card flex flex-col w-[calc(50%-var(--space-8))] tablet:w-[236px] rounded-[var(--radius-12)] overflow-hidden transition-transform group-hover:scale-[1.02]">
              <div className="w-full aspect-[3/4] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
                <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50" />
              </div>
              <div className="flex flex-col justify-between flex-1 pt-[var(--space-12)] pb-[var(--space-16)] px-[var(--space-12)]">
                <div className="flex flex-col gap-[var(--space-8)]">
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[#E6EEF8] font-medium">{selected.style.name}</span>
                    <span className="flex items-center gap-1">
                      <span className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-brand-primary)] font-semibold">{selected.afterScore.toFixed(2)}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full glass-progress-track overflow-hidden">
                    <div className="h-full rounded-full glass-progress-fill" style={{ width: `${(selected.afterScore / 10) * 100}%` }} />
                  </div>
                </div>
                <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] italic text-[var(--color-text-secondary)] line-clamp-2 mt-[var(--space-8)]">
                  &laquo;{selected.shortReview}&raquo;
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Review modal / slider */}
      {!isComingSoon && (
        <ReviewModal
          testimonials={testimonials}
          initialIndex={modalIdx}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
        />
      )}
    </section>
  );
}
