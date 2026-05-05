import { useEffect, useMemo, useRef, useState } from 'react';
import TestimonialShowcaseCard from '../components/TestimonialShowcaseCard';
import { type PlaceholderTone } from '../components/effects/PlaceholderArt';
import type { Testimonial } from '../data/testimonials';

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
        isCompact ? 'py-[40px] tablet:py-[56px]' : 'landing-section-py'
      }`}
      onMouseEnter={() => pause(2000)}
      onMouseLeave={() => pause(0)}
    >
      <div className="mx-auto flex w-full max-w-[1200px] flex-col items-center gap-[var(--space-32)] tablet:gap-[var(--space-48)]">
        <div className="reveal flex flex-col items-center gap-[var(--space-8)] text-center">
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
                  <TestimonialShowcaseCard
                    key={item.id}
                    item={item}
                    isActive={isActive}
                    withSlider={withSlider}
                    reducedMotion={reducedMotion}
                    tone={tone}
                    playMode="autoCycle"
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
