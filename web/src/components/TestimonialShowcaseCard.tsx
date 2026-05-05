import BeforeAfterSlider from './BeforeAfterSlider';
import {
  PlaceholderUpload,
  PlaceholderUpgrade,
  type PlaceholderTone,
} from './effects/PlaceholderArt';
import { CATEGORIES } from '../data/styles';
import { FULL_LANDING_STYLES_BY_CATEGORY } from '../data/landingStyles';
import type { Testimonial, TestimonialTier } from '../data/testimonials';

/**
 * 1.50.1: Единая визуальная карточка для двух мест:
 *  - карусель `Testimonials` (играет cross-fade автоматически на
 *    активном слоте; режим ``autoCycle``);
 *  - правая часть `Simulation` (cross-fade триггерится при выборе
 *    нового стиля; режим ``playKey``).
 *
 * Раньше эти места имели разную верстку (avatar + chips + emoji
 * vs. голый slider + score-row + отдельный review-блок). Теперь
 * один компонент рендерит идентичный layout на обоих лендингах,
 * меняется только триггер старта анимации слайдера.
 */

function getDirectionLabel(item: Testimonial): string {
  const categoryLabel =
    item.category === 'documents'
      ? 'Документы'
      : CATEGORIES.find((c) => c.id === item.category)?.label ?? item.category;
  const styleName =
    item.category === 'documents'
      ? ''
      : FULL_LANDING_STYLES_BY_CATEGORY[item.category]?.find((s) => s.key === item.styleKey)?.name ?? '';
  return styleName ? `${categoryLabel} · «${styleName}»` : categoryLabel;
}

function avatarUrl(item: Testimonial): string {
  const seed = encodeURIComponent(item.avatarSeed ?? item.nickname.replace(/^@/, ''));
  return `https://api.dicebear.com/9.x/notionists/svg?seed=${seed}&radius=50&backgroundType=gradientLinear`;
}

function getInitial(nickname: string): string {
  const cleaned = nickname.replace(/^@/, '');
  return (cleaned[0] ?? '?').toUpperCase();
}

export interface TestimonialShowcaseCardProps {
  item: Testimonial;
  /** Слайдер до/после внутри карточки. По умолчанию виден. */
  withSlider?: boolean;
  /** Тон placeholder'ов внутри слайдера. */
  tone?: PlaceholderTone;
  /** OS prefers-reduced-motion — отключает auto-fade. */
  reducedMotion?: boolean;
  /**
   * Режим анимации слайдера:
   *  - ``autoCycle``: один кросс-фейд при mount (карусель пере-mount'ит
   *    карточку при advance, благодаря этому fade рестартует);
   *  - ``playKey``: фейд триггерится при изменении ``playKey``.
   *    На первом mount показываем сразу «после».
   */
  playMode?: 'autoCycle' | 'playKey';
  /** В режиме ``autoCycle`` указывает, активен ли слот сейчас. */
  isActive?: boolean;
  /** В режиме ``playKey`` — ключ, смена которого запускает кросс-фейд. */
  playKey?: string | number;
}

export default function TestimonialShowcaseCard({
  item,
  withSlider = true,
  tone,
  reducedMotion = false,
  playMode = 'autoCycle',
  isActive = false,
  playKey,
}: TestimonialShowcaseCardProps) {
  const direction = getDirectionLabel(item);
  const tier: TestimonialTier = item.tier ?? 'Обычный';

  return (
    <article className={`testimonial-card ${isActive ? 'is-active' : ''} gradient-border-card rounded-[var(--radius-12)]`}>
      <header className="flex items-center gap-[var(--space-12)]">
        <div className="testimonial-avatar shrink-0">
          <img
            src={avatarUrl(item)}
            alt=""
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none';
            }}
          />
          <span aria-hidden="true" className="testimonial-avatar-fallback">
            {getInitial(item.nickname)}
          </span>
        </div>
        <div className="flex flex-col gap-[var(--space-4)] min-w-0">
          <div className="text-[15px] tablet:text-[16px] leading-[20px] tablet:leading-[22px] font-semibold text-[var(--color-text-primary)] truncate">
            {item.nickname}
          </div>
          <div className="flex flex-wrap items-center gap-[6px]">
            <span className="testimonial-chip testimonial-chip--direction">{direction}</span>
            <span className={`testimonial-chip testimonial-chip--tier ${tier === 'Премиум' ? 'is-premium' : 'is-regular'}`}>
              {tier === 'Премиум' && <span aria-hidden="true" className="testimonial-chip-spark">✦</span>}
              {tier}
            </span>
          </div>
        </div>
      </header>

      <p className="testimonial-emoji-review landing-body text-[var(--color-text-primary)]">
        {item.emojiReview ?? item.shortReview}
      </p>

      {withSlider && (
        <div className="testimonial-slider-wrap rounded-[var(--radius-12)] overflow-hidden aspect-[3/4]">
          {playMode === 'autoCycle' ? (
            <BeforeAfterSlider
              before={<PlaceholderUpload tone={tone} className="w-full h-full opacity-90 text-[var(--color-text-secondary)]" />}
              after={<PlaceholderUpgrade tone={tone} className="w-full h-full opacity-100 text-[var(--color-brand-primary)]" />}
              autoCycle={isActive && !reducedMotion}
              autoCycleMs={3000}
              autoHoldMs={3000}
              hideHandle
              hideLabels
            />
          ) : (
            <BeforeAfterSlider
              playKey={playKey}
              autoCycleMs={3000}
              before={<PlaceholderUpload tone={tone} className="w-full h-full opacity-90 text-[var(--color-text-secondary)]" />}
              after={<PlaceholderUpgrade tone={tone} className="w-full h-full opacity-100 text-[var(--color-brand-primary)]" />}
              hideHandle
              hideLabels
            />
          )}
        </div>
      )}
    </article>
  );
}
