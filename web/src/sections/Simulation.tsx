import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CATEGORIES, COMING_SOON_CATEGORIES, getMockDelta, type CategoryId } from '../data/styles';
import { DOCUMENT_LANDING_ITEMS, FULL_LANDING_STYLES_BY_CATEGORY } from '../data/landingStyles';
import { getStyleShowcaseReview, type ReviewCategory } from '../data/testimonials';
import type { StyleItem } from '../data/styles';
import CategoryTabs from '../components/CategoryTabs';
import TestimonialShowcaseCard from '../components/TestimonialShowcaseCard';
import { useApp } from '../context/AppContext';
import { findBlock, type LandingPage } from '../lib/landing-cms';

// 1.50.1: 8 строк под высоту правой колонки (карточка
// TestimonialShowcaseCard ~660 px на десктопе с aspect-[3/4]
// слайдером 420 → 560 px). 8 × 52 + 7 × 20 + 12 + 44 = 612 px.
const ITEMS_PER_PAGE = 8;
const PLACEHOLDER_TONE_BY_CATEGORY: Record<ReviewCategory, 'home' | 'dating' | 'cv' | 'documents'> = {
  social: 'home',
  cv: 'cv',
  dating: 'dating',
  model: 'home',
  brand: 'home',
  memes: 'home',
  documents: 'documents',
};

interface SimulationProps {
  cmsPage?: LandingPage | null;
  /**
   * 1.50.0: на сценарных лендингах табы направлений выключаем —
   * там одно фиксированное направление (`forceCategory`) и только
   * выбор стиля справа.
   */
  showCategoryTabs?: boolean;
  /**
   * Если задано — секция работает в режиме «одного направления»:
   * activeCategory из глобального стейта игнорируется, табы скрыты,
   * стили/отзывы берутся для переданной категории.
   */
  forceCategory?: ReviewCategory;
}

function getStylesFor(category: ReviewCategory): StyleItem[] {
  if (category === 'documents') return DOCUMENT_LANDING_ITEMS;
  return FULL_LANDING_STYLES_BY_CATEGORY[category];
}

export default function Simulation({
  cmsPage,
  showCategoryTabs = true,
  forceCategory,
}: SimulationProps = {}) {
  const { activeCategory, setActiveCategory } = useApp();
  const { t } = useTranslation('landing');
  const category: ReviewCategory = forceCategory ?? activeCategory;
  const [selectedIdx, setSelectedIdx] = useState(0);

  const styles = getStylesFor(category);
  const visibleStyles = useMemo(() => styles.slice(0, ITEMS_PER_PAGE), [styles]);
  const remaining = Math.max(0, styles.length - ITEMS_PER_PAGE);
  const selectedStyle = visibleStyles[selectedIdx] ?? visibleStyles[0];

  // 1.50.1: правая часть — общая карточка TestimonialShowcaseCard
  // (тот же layout, что у карусели Testimonials). При клике по
  // стилю меняется playKey → внутри слайдер делает один cross-fade.
  // Отзыв подбирается из `style-showcase` пула — он не пересекается
  // с carousel-отзывами.
  const showcaseReview = useMemo(
    () => (selectedStyle ? getStyleShowcaseReview(category, selectedStyle.key) : undefined),
    [category, selectedStyle],
  );

  const tone = PLACEHOLDER_TONE_BY_CATEGORY[category] ?? 'home';

  // Только для главного лендинга: подсказка «скоро» внутри секции.
  const isComingSoon =
    !forceCategory && COMING_SOON_CATEGORIES.includes(activeCategory) && showCategoryTabs;
  const categoryLabel = CATEGORIES.find((c) => c.id === activeCategory)?.label ?? activeCategory;

  const cmsBlock = findBlock(cmsPage ?? undefined, 'six_categories');
  const cmsData = (cmsBlock?.data ?? {}) as Record<string, unknown>;
  const title = typeof cmsData.title === 'string' && cmsData.title ? cmsData.title : t('simulation.title');
  const subtitle = typeof cmsData.subtitle === 'string' && cmsData.subtitle ? cmsData.subtitle : t('simulation.subtitle');
  const lead = typeof cmsData.lead === 'string' && cmsData.lead ? cmsData.lead : t('simulation.lead');
  const sublead = typeof cmsData.sublead === 'string' && cmsData.sublead ? cmsData.sublead : t('simulation.sublead');

  function handleCategoryChange(id: CategoryId) {
    setActiveCategory(id);
    setSelectedIdx(0);
  }

  return (
    <section
      id="стили"
      className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py"
      style={{ minHeight: '100vh' }}
    >
      {/* Heading */}
      <div className="reveal relative flex flex-col items-center gap-[var(--space-12)] text-center">
        <h2 className="landing-h2 text-[var(--color-text-primary)]">{title}</h2>
        <h2
          className="landing-h2"
          style={{
            background:
              'linear-gradient(103deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          {subtitle}
        </h2>
        <p className="landing-lead max-w-[696px]">{lead}</p>
        <p className="landing-lead max-w-[660px]">{sublead}</p>
      </div>

      {/* Category tabs — main landing only. 1.50.0: фоновая плашка
          снаружи убрана внутри CategoryTabs; coming-soon скрыты. */}
      {showCategoryTabs && (
        <div className="relative flex items-center justify-center w-full">
          <CategoryTabs
            active={activeCategory}
            onChange={handleCategoryChange}
            hideComingSoon
          />
        </div>
      )}

      {/* Coming-soon stub (только основной лендинг, на случай если
          вернём направления, которые ещё не готовы) */}
      {isComingSoon && (
        <div className="flex flex-col items-center gap-[var(--space-24)] w-full max-w-[600px] py-[var(--space-32)]">
          <div className="gradient-border-card glass-card flex flex-col items-center justify-center gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-32)] w-full">
            <span className="text-[48px]">🚧</span>
            <h3 className="text-[24px] tablet:text-[32px] font-semibold text-[var(--color-text-primary)]">
              {categoryLabel}
            </h3>
            <p className="text-[16px] leading-[24px] text-[var(--color-text-secondary)] text-center max-w-[400px]">
              {t('simulation.comingSoonText')}
            </p>
            <Link
              to="/app"
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[22px] rounded-[var(--radius-pill)] font-medium no-underline mt-[var(--space-8)]"
            >
              {t('simulation.tryOtherStyles')}
            </Link>
          </div>
        </div>
      )}

      {/* Style list + showcase card */}
      {!isComingSoon && selectedStyle && (
        <div className="relative flex flex-col desktop:flex-row items-stretch desktop:items-start desktop:justify-between w-full max-w-[1200px] gap-[var(--space-24)] desktop:gap-[70px]">
          {/* Style list (left) */}
          <div className="flex flex-col gap-[var(--space-20)] w-full desktop:flex-1 desktop:max-w-[560px] order-last desktop:order-first">
            {visibleStyles.map((style, i) => (
              <button
                key={style.key}
                type="button"
                onClick={() => setSelectedIdx(i)}
                className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all text-left ${
                  selectedIdx === i ? 'glass-row-active' : 'glass-row'
                }`}
                style={
                  {
                    '--gb-color':
                      selectedIdx === i
                        ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)'
                        : 'var(--glass-border-hover)',
                  } as React.CSSProperties
                }
              >
                <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">
                  {style.icon}
                </div>
                <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                  <span className="text-[16px] leading-[24px] text-[var(--color-text-primary)] font-medium truncate">
                    {style.name}
                  </span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">
                    {style.desc}
                  </span>
                </div>
                <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                  {getMockDelta(style.deltaRange, style.key)}
                </span>
              </button>
            ))}

            {remaining > 0 && (
              <Link
                to="/app"
                className="glass-btn-secondary flex items-center justify-center w-full px-[var(--space-20)] py-[var(--space-10)] rounded-[var(--radius-12)] text-[var(--color-brand-primary)] text-[16px] leading-[24px] font-medium no-underline"
              >
                {t('simulation.moreStyles', { count: remaining })}
              </Link>
            )}
          </div>

          {/* Showcase card (right): тот же визуальный язык, что в
              карусели Testimonials. На клик по стилю слева слайдер
              внутри карточки делает один кросс-фейд. */}
          <div className="flex flex-col w-full desktop:max-w-[420px] order-first desktop:order-last">
            {showcaseReview ? (
              <TestimonialShowcaseCard
                item={showcaseReview}
                tone={tone}
                playMode="playKey"
                playKey={selectedStyle.key}
                withSlider
              />
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
