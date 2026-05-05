import { useEffect, useMemo, useRef, useState } from 'react';
import BeforeAfterSlider from '../components/BeforeAfterSlider';
import {
  PlaceholderUpload,
  PlaceholderUpgrade,
  type PlaceholderTone,
} from '../components/effects/PlaceholderArt';
import { CATEGORIES } from '../data/styles';
import { FULL_LANDING_STYLES_BY_CATEGORY } from '../data/landingStyles';
import type { Testimonial, TestimonialTier } from '../data/testimonials';

export type { Testimonial } from '../data/testimonials';

export interface TestimonialsProps {
  /** Reviews to render in the carousel. */
  items: Testimonial[];
  /** Block heading; defaults to "Впечатления пользователей". */
  title?: string;
  /** Optional eyebrow over the title. */
  eyebrow?: string;
  /**
   * Time the active card stays on screen before the carousel advances
   * (ms). Includes the slider sweep + hold phases and a small
   * cross-fade buffer.
   */
  rotationMs?: number;
  /**
   * `compact` removes the left/right preview slots and uses a smaller
   * visual cap — meant for scenario landings where the carousel is a
   * supporting block rather than a hero block.
   */
  variant?: 'default' | 'compact';
  /**
   * When false, hide the before/after slider (used for the documents
   * scenario landing where there's no meaningful "after" image).
   */
  withSlider?: boolean;
  /**
   * Тематический tone для plaaceholder before/after (rose / violet /
   * neutral) — позволяет визуально отличать «фото» в карточках на
   * разных лендингах при единой реализации слайдера.
   */
  tone?: PlaceholderTone;
}

const DEFAULT_ROTATION_MS = 6500;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const m = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(m.matches);
    update();
    m.addEventListener('change', update);
    return () => m.removeEventListener('change', update);
  }, []);
  return reduced;
}

function getDirectionLabel(item: Testimonial): string {
  const categoryLabel = CATEGORIES.find((c) => c.id === item.category)?.label ?? item.category;
  const styleName =
    FULL_LANDING_STYLES_BY_CATEGORY[item.category]?.find((s) => s.key === item.styleKey)?.name ?? '';
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

interface CardProps {
  item: Testimonial;
  isActive: boolean;
  withSlider: boolean;
  reducedMotion: boolean;
  tone?: PlaceholderTone;
}

function TestimonialCard({ item, isActive, withSlider, reducedMotion, tone }: CardProps) {
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
          <BeforeAfterSlider
            // Re-mount on item change so the cross-fade restarts
            // cleanly when the carousel advances.
            key={item.id}
            before={<PlaceholderUpload tone={tone} className="w-full h-full opacity-90 text-[var(--color-text-secondary)]" />}
            after={<PlaceholderUpgrade tone={tone} className="w-full h-full opacity-100 text-[var(--color-brand-primary)]" />}
            autoCycle={isActive && !reducedMotion}
            autoCycleMs={3000}
            autoHoldMs={3000}
            hideHandle
            hideLabels
          />
        </div>
      )}
    </article>
  );
}

/**
 * Carousel of social-proof reviews used on the home landing and the
 * scenario landings (Dating, Resume, Documents). Each card carries
 * an avatar, nickname, direction/style chip, tier badge, an
 * emoji-rich short review and an auto-cycling before/after slider.
 *
 * Carousel logic:
 *   - one card stays "active" (centered, full opacity) for
 *     `rotationMs` — long enough to play one full sweep + hold of the
 *     before/after slider;
 *   - prev/next are visible at reduced opacity / scale on the sides
 *     (default variant) or fully hidden (compact variant);
 *   - on hover or drag the rotation pauses and resumes 1.5s after the
 *     last interaction;
 *   - prefers-reduced-motion freezes the carousel on the active card
 *     and disables the slider sweep.
 */
export default function Testimonials({
  items,
  title = 'Впечатления пользователей',
  eyebrow,
  rotationMs = DEFAULT_ROTATION_MS,
  variant = 'default',
  withSlider = true,
  tone,
}: TestimonialsProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [activeIndex, setActiveIndex] = useState(0);
  const pausedUntilRef = useRef<number>(0);

  const total = items.length;
  const isCompact = variant === 'compact';

  useEffect(() => {
    setActiveIndex(0);
  }, [items]);

  useEffect(() => {
    if (reducedMotion || total <= 1) return;
    const tick = () => {
      if (performance.now() < pausedUntilRef.current) return;
      setActiveIndex((i) => (i + 1) % total);
    };
    const id = window.setInterval(tick, rotationMs);
    return () => window.clearInterval(id);
  }, [reducedMotion, rotationMs, total]);

  const pause = (durationMs = 4000) => {
    pausedUntilRef.current = performance.now() + durationMs;
  };

  const slots = useMemo(() => {
    if (total === 0) return [];
    const visibleRadius = isCompact ? 0 : 1;
    return items
      .map((item, i) => {
        let offset = i - activeIndex;
        if (offset > total / 2) offset -= total;
        if (offset < -total / 2) offset += total;
        return { item, offset };
      })
      // Only mount cards close to the active index — far slots are
      // invisible anyway and we'd otherwise pay for N DiceBear avatar
      // requests up front.
      .filter(({ offset }) => Math.abs(offset) <= visibleRadius);
  }, [items, activeIndex, total, isCompact]);

  if (total === 0) return null;

  return (
    <section
      className={`relative z-[2] px-[var(--space-16)] tablet:px-[var(--space-24)] ${
        isCompact ? 'py-[40px] tablet:py-[56px]' : 'py-[60px] tablet:py-[88px]'
      }`}
      onMouseEnter={() => pause(2000)}
      onMouseLeave={() => pause(0)}
    >
      <div className="mx-auto flex w-full max-w-[1200px] flex-col items-center gap-[var(--space-24)]">
        <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
          {eyebrow && (
            <span className="text-[12px] tablet:text-[13px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
              {eyebrow}
            </span>
          )}
          <h2 className="landing-h2 text-[var(--color-text-primary)]">{title}</h2>
        </div>

        <div className={`testimonial-carousel ${isCompact ? 'is-compact' : ''}`}>
          <div className="testimonial-track">
            {slots.map(({ item, offset }) => {
              const abs = Math.abs(offset);
              const isActive = offset === 0;
              const visible = isCompact ? isActive : abs <= 1;
              const slotClass = isActive
                ? 'is-active'
                : offset === -1
                  ? 'is-prev'
                  : offset === 1
                    ? 'is-next'
                    : offset < 0
                      ? 'is-far-prev'
                      : 'is-far-next';
              return (
                <div
                  key={item.id}
                  className={`testimonial-slot ${slotClass}`}
                  aria-hidden={!isActive}
                  style={{ pointerEvents: isActive ? 'auto' : 'none', opacity: visible ? undefined : 0 }}
                >
                  <TestimonialCard
                    item={item}
                    isActive={isActive}
                    withSlider={withSlider}
                    reducedMotion={reducedMotion}
                    tone={tone}
                  />
                </div>
              );
            })}
          </div>

          {total > 1 && total <= 8 && (
            <div className="testimonial-dots" role="tablist" aria-label="Отзывы">
              {items.map((it, i) => (
                <button
                  key={it.id}
                  type="button"
                  role="tab"
                  aria-selected={i === activeIndex}
                  aria-label={`Отзыв ${i + 1} из ${total}`}
                  className={`testimonial-dot ${i === activeIndex ? 'is-active' : ''}`}
                  onClick={() => {
                    setActiveIndex(i);
                    pause(8000);
                  }}
                />
              ))}
            </div>
          )}
          {total > 8 && (
            <div className="testimonial-dots-compact" aria-live="polite">
              <span className="testimonial-dots-compact-count">
                {activeIndex + 1} / {total}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
