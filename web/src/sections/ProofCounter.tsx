import { useEffect, useRef, useState } from 'react';
import type { SocialProofCounterConfig } from '../data/social-proof';

export interface ProofCounterProps {
  /**
   * Стартовое значение счётчика. Дальше идёт ленивый рост по
   * `counter` (random tick + редкие burst-всплески).
   */
  baseCount: number;
  /** Параметры псевдослучайного тика — те же, что в SocialProof. */
  counter: SocialProofCounterConfig;
  /**
   * Основная подпись под цифрой. Должна звучать грамотно с любой
   * цифрой — то есть писать после числительного только
   * несклоняемые («фото», «AI-фото») и нейтральные хвосты.
   * Пример: "AI-фото уже сделано пользователями Look Studio".
   */
  caption: string;
  /** Опциональный подзаголовок над цифрой (eyebrow). */
  eyebrow?: string;
  /** Опциональный мелкий хвост под caption. */
  subcaption?: string;
}

const DEFAULT_COUNTER: SocialProofCounterConfig = {
  minDelayMs: 8000,
  maxDelayMs: 36000,
  burstChance: 0.16,
  maxBurstSize: 3,
};

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function formatCounter(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}

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
 * Standalone proof block: heart icon (which beats on every counter
 * tick) → big number → grammatical caption underneath. Splits
 * the old combined SocialProof into a pure proof part and a
 * separate testimonials feed.
 */
export default function ProofCounter({
  baseCount,
  counter = DEFAULT_COUNTER,
  caption,
  eyebrow,
  subcaption,
}: ProofCounterProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [count, setCount] = useState(baseCount);
  // Re-mount key for the heart node — bumping this restarts the CSS
  // pop animation on every counter increment, regardless of whether
  // the previous animation had finished.
  const [beatKey, setBeatKey] = useState(0);
  const lastBaseRef = useRef(baseCount);

  // External baseCount changes (e.g. CMS reload) reset the counter
  // to keep behaviour predictable.
  useEffect(() => {
    if (lastBaseRef.current !== baseCount) {
      lastBaseRef.current = baseCount;
      setCount(baseCount);
    }
  }, [baseCount]);

  useEffect(() => {
    if (reducedMotion) return;
    let cancelled = false;
    let timeoutId: number | undefined;

    const scheduleTick = () => {
      const delay = randomInt(counter.minDelayMs, counter.maxDelayMs);
      timeoutId = window.setTimeout(() => {
        if (cancelled) return;
        const burstTriggered = Math.random() < counter.burstChance;
        const increment = burstTriggered
          ? randomInt(2, Math.max(2, counter.maxBurstSize))
          : 1;
        setCount((current) => current + increment);
        setBeatKey((k) => k + 1);
        scheduleTick();
      }, delay);
    };

    scheduleTick();
    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [counter, reducedMotion]);

  return (
    <section className="relative z-[2] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[88px]">
      <div className="mx-auto flex max-w-[760px] flex-col items-center gap-[var(--space-16)] text-center">
        {eyebrow && (
          <span className="text-[12px] tablet:text-[13px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            {eyebrow}
          </span>
        )}

        <div className="relative flex items-center justify-center">
          {/* Heart pulses on every increment. We re-key the wrapper so
              the CSS animation restarts even if it was mid-flight. */}
          <span
            key={beatKey}
            aria-hidden="true"
            className={`proof-heart ${reducedMotion ? '' : 'proof-heart-beat'} mr-[var(--space-12)] tablet:mr-[var(--space-16)] inline-flex shrink-0`}
          >
            <svg
              viewBox="0 0 24 24"
              fill="currentColor"
              className="w-[40px] h-[40px] tablet:w-[56px] tablet:h-[56px] desktop:w-[64px] desktop:h-[64px]"
            >
              <path d="M12 21s-7-4.35-9.33-9.04C1.32 9.13 2.66 5.6 6.07 5.05c2.05-.33 3.94.74 4.93 2.4.99-1.66 2.88-2.73 4.93-2.4 3.41.55 4.75 4.08 3.4 6.91C19 16.65 12 21 12 21Z" />
            </svg>
          </span>

          <span className="proof-counter-value text-[64px] tablet:text-[112px] desktop:text-[140px] font-semibold leading-none text-[var(--color-brand-primary)] tabular-nums">
            {formatCounter(count)}
          </span>
        </div>

        <p className="text-[16px] tablet:text-[20px] desktop:text-[22px] leading-[1.45] text-[var(--color-text-secondary)] max-w-[640px]">
          {caption}
        </p>

        {subcaption && (
          <p className="text-[13px] tablet:text-[14px] leading-[1.45] text-[var(--color-text-muted)] max-w-[560px]">
            {subcaption}
          </p>
        )}
      </div>
    </section>
  );
}
