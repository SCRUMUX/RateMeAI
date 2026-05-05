import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CATEGORIES, COMING_SOON_CATEGORIES, getMockDelta, type CategoryId } from '../data/styles';
import { DOCUMENT_LANDING_ITEMS, FULL_LANDING_STYLES_BY_CATEGORY } from '../data/landingStyles';
import { getStyleShowcaseReview, type ReviewCategory } from '../data/testimonials';
import type { StyleItem } from '../data/styles';
import CategoryTabs from '../components/CategoryTabs';
import BeforeAfterSlider from '../components/BeforeAfterSlider';
import { PlaceholderUpload, PlaceholderUpgrade } from '../components/effects/PlaceholderArt';
import { useApp } from '../context/AppContext';
import { findBlock, type LandingPage } from '../lib/landing-cms';

const ITEMS_PER_PAGE = 5;
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
  const category: ReviewCategory = forceCategory ?? activeCategory;
  const [selectedIdx, setSelectedIdx] = useState(0);

  const styles = getStylesFor(category);
  const visibleStyles = useMemo(() => styles.slice(0, ITEMS_PER_PAGE), [styles]);
  const remaining = Math.max(0, styles.length - ITEMS_PER_PAGE);
  const selectedStyle = visibleStyles[selectedIdx] ?? visibleStyles[0];

  // 1.50.0: правая часть теперь — слайдер до/после + отзыв под ним.
  // Отзыв берём из `style-showcase` пула (не пересекается с
  // основной каруселью Testimonials).
  const showcaseReview = useMemo(
    () => (selectedStyle ? getStyleShowcaseReview(category, selectedStyle.key) : undefined),
    [category, selectedStyle],
  );

  const beforeScore = showcaseReview?.beforeScore ?? 5.6;
  const afterScore = showcaseReview?.afterScore ?? 6.7;
  const tone = PLACEHOLDER_TONE_BY_CATEGORY[category] ?? 'home';

  // Только для главного лендинга: подсказка «скоро» внутри секции.
  const isComingSoon =
    !forceCategory && COMING_SOON_CATEGORIES.includes(activeCategory) && showCategoryTabs;
  const categoryLabel = CATEGORIES.find((c) => c.id === activeCategory)?.label ?? activeCategory;

  const cmsBlock = findBlock(cmsPage ?? undefined, 'six_categories');
  const cmsData = (cmsBlock?.data ?? {}) as Record<string, unknown>;
  // 1.50.0: дефолт заголовка изменён с «6 категорий» на
  // «Улучшаем фото» — суть та же, формулировка лучше работает.
  const title = typeof cmsData.title === 'string' ? cmsData.title : 'Улучшаем фото';
  const subtitle = typeof cmsData.subtitle === 'string' ? cmsData.subtitle : '— под любую задачу';
  const lead =
    typeof cmsData.lead === 'string'
      ? cmsData.lead
      : 'В каждой категории — более 100 уникальных стилей. Каждая генерация улучшает психологию восприятия';
  const sublead =
    typeof cmsData.sublead === 'string'
      ? cmsData.sublead
      : 'Каждый стиль генерирует новое фото и улучшает психологию восприятия для конкретной жизненной ситуации';

  function handleCategoryChange(id: CategoryId) {
    setActiveCategory(id);
    setSelectedIdx(0);
  }

  return (
    <section
      id="стили"
      className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-96)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[120px]"
      style={{ minHeight: '100vh' }}
    >
      {/* Heading */}
      <div className="relative flex flex-col items-center gap-[var(--space-12)] text-center">
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

      {/* Style list + slider with showcase review */}
      {!isComingSoon && selectedStyle && (
        <div className="relative flex flex-col desktop:flex-row items-stretch desktop:items-start desktop:justify-between w-full max-w-[1200px] gap-[var(--space-24)] desktop:gap-[70px]">
          {/* Style list (left) */}
          <div className="flex flex-col gap-[var(--space-12)] w-full desktop:flex-1 desktop:max-w-[588px] order-last desktop:order-first">
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
                className="glass-btn-secondary flex items-center justify-center w-full mt-[var(--space-12)] px-[var(--space-20)] py-[var(--space-10)] rounded-[var(--radius-12)] text-[var(--color-brand-primary)] text-[16px] leading-[24px] font-medium no-underline"
              >
                Ещё {remaining} образов
              </Link>
            )}
          </div>

          {/* Slider + review (right) */}
          <div className="flex flex-col gap-[var(--space-16)] w-full desktop:max-w-[440px] order-first desktop:order-last">
            <div className="gradient-border-card glass-card rounded-[var(--radius-12)] overflow-hidden aspect-[3/4]">
              <BeforeAfterSlider
                playKey={selectedStyle.key}
                autoCycleMs={3000}
                hideHandle
                hideLabels={false}
                labelBefore="Исходное"
                labelAfter={selectedStyle.name}
                before={
                  <div className="w-full h-full flex items-center justify-center bg-[var(--glass-surface-soft)]">
                    <PlaceholderUpload
                      tone={tone}
                      className="w-full h-full opacity-50 text-[var(--color-text-secondary)]"
                    />
                  </div>
                }
                after={
                  <div className="w-full h-full flex items-center justify-center bg-[var(--glass-surface-soft)]">
                    <PlaceholderUpgrade
                      tone={tone}
                      className="w-full h-full opacity-70 text-[var(--color-text-secondary)]"
                    />
                  </div>
                }
              />
            </div>

            {/* Score row */}
            <div className="flex items-center gap-[var(--space-12)]">
              <div className="flex flex-col flex-1 gap-[var(--space-4)] glass-card rounded-[var(--radius-8)] px-[var(--space-12)] py-[var(--space-10)]">
                <span className="text-[12px] leading-[14px] text-[var(--color-text-muted)]">Исходное</span>
                <span className="text-[16px] leading-[20px] text-[var(--color-text-secondary)] font-medium tabular-nums">
                  {beforeScore.toFixed(2)}
                  <span className="text-[11px] text-[var(--color-text-muted)]"> / 10</span>
                </span>
              </div>
              <div className="flex flex-col flex-1 gap-[var(--space-4)] glass-card rounded-[var(--radius-8)] px-[var(--space-12)] py-[var(--space-10)]">
                <span className="text-[12px] leading-[14px] text-[var(--color-text-muted)]">{selectedStyle.name}</span>
                <span className="text-[16px] leading-[20px] text-[var(--color-brand-primary)] font-semibold tabular-nums">
                  {afterScore.toFixed(2)}
                  <span className="text-[11px] text-[var(--color-text-muted)]"> / 10</span>
                </span>
              </div>
            </div>

            {/* Showcase review under the slider */}
            {showcaseReview && (
              <div className="glass-card rounded-[var(--radius-12)] px-[var(--space-16)] py-[var(--space-14)] flex flex-col gap-[var(--space-8)]">
                <div className="flex items-center gap-[var(--space-8)]">
                  <span className="text-[14px] leading-[18px] text-[var(--color-text-primary)] font-medium truncate">
                    {showcaseReview.nickname}
                  </span>
                  {showcaseReview.tier && (
                    <span className="px-[var(--space-6)] py-[1px] rounded-[var(--radius-pill)] text-[10px] leading-[14px] uppercase tracking-wide text-[var(--color-text-secondary)] glass-badge-cyan">
                      {showcaseReview.tier}
                    </span>
                  )}
                </div>
                <p className="text-[13px] leading-[18px] text-[var(--color-text-secondary)] italic">
                  «{showcaseReview.shortReview}»
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
