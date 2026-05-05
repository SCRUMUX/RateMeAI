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
   * Крупный белый заголовок под цифрой (H2). Должен звучать
   * грамотно с любой цифрой — несклоняемое «фото» + «уже создано/
   * сделано» работают для всех чисел.
   */
  heading: string;
  /** Опциональный обычный абзац под H2. */
  subheading?: string;
}

interface BurstParticle {
  id: number;
  x: number;
  size: number;
  delay: number;
  hue: 'primary' | 'secondary';
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

function randomFloat(min: number, max: number): number {
  return Math.random() * (max - min) + min;
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

const HEART_PATH =
  'M12 21s-7-4.35-9.33-9.04C1.32 9.13 2.66 5.6 6.07 5.05c2.05-.33 3.94.74 4.93 2.4.99-1.66 2.88-2.73 4.93-2.4 3.41.55 4.75 4.08 3.4 6.91C19 16.65 12 21 12 21Z';

/**
 * Standalone proof block: heart icon (which beats on every counter
 * tick) → big number with primary gradient → bold heading → optional
 * paragraph. On every tick we additionally spawn a small burst of
 * hearts that fly upward and dissolve, TikTok-style.
 *
 * The optional radial glow inside the section (also keyed off every
 * tick) provides a subtle background reaction without touching the
 * page-wide Fluid/Energy/Mesh effects — `isolation: isolate` keeps
 * the flash contained.
 */
export default function ProofCounter({
  baseCount,
  counter = DEFAULT_COUNTER,
  heading,
  subheading,
}: ProofCounterProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [count, setCount] = useState(baseCount);
  // Re-mount key for the static heart node — bumping this restarts
  // the CSS pop animation on every counter increment, regardless of
  // whether the previous animation had finished.
  const [beatKey, setBeatKey] = useState(0);
  // Re-mount key for the section glow flash.
  const [burstKey, setBurstKey] = useState(0);
  const [particles, setParticles] = useState<BurstParticle[]>([]);
  const nextIdRef = useRef(0);
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
        setBurstKey((k) => k + 1);

        const particleCount = burstTriggered
          ? randomInt(2, Math.max(2, counter.maxBurstSize))
          : 1;
        const newOnes: BurstParticle[] = [];
        for (let i = 0; i < particleCount; i++) {
          const id = nextIdRef.current++;
          newOnes.push({
            id,
            x: randomInt(-26, 26),
            size: randomFloat(0.7, 1.15),
            delay: randomInt(0, 140),
            hue: id % 2 === 0 ? 'primary' : 'secondary',
          });
        }
        setParticles((arr) => [...arr, ...newOnes]);

        scheduleTick();
      }, delay);
    };

    scheduleTick();
    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [counter, reducedMotion]);

  const removeParticle = (id: number) => {
    setParticles((arr) => arr.filter((p) => p.id !== id));
  };

  return (
    <section className="proof-counter-section relative z-[2] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[88px]">
      {!reducedMotion && (
        <div
          key={burstKey}
          aria-hidden="true"
          className="proof-counter-glow"
        />
      )}

      <div className="relative z-[1] mx-auto flex max-w-[760px] flex-col items-center text-center">
        <div className="proof-counter-row relative flex items-center justify-center">
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
              <path d={HEART_PATH} />
            </svg>
          </span>

          <span className="proof-counter-value text-[64px] tablet:text-[112px] desktop:text-[140px] font-semibold leading-none tabular-nums">
            {formatCounter(count)}
          </span>

          {!reducedMotion && (
            <div className="proof-burst-layer pointer-events-none absolute inset-0 overflow-visible">
              {particles.map((p) => (
                <span
                  key={p.id}
                  aria-hidden="true"
                  className={`proof-burst-particle ${p.hue}`}
                  style={
                    {
                      '--x': `${p.x}px`,
                      '--scale': `${p.size}`,
                      animationDelay: `${p.delay}ms`,
                    } as React.CSSProperties
                  }
                  onAnimationEnd={() => removeParticle(p.id)}
                >
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
                    <path d={HEART_PATH} />
                  </svg>
                </span>
              ))}
            </div>
          )}
        </div>

        <h2 className="text-[28px] tablet:text-[40px] desktop:text-[48px] font-semibold leading-[1.1] text-[var(--color-text-primary)] mt-[var(--space-16)] tablet:mt-[var(--space-24)] max-w-[640px]">
          {heading}
        </h2>

        {subheading && (
          <p className="text-[16px] tablet:text-[20px] desktop:text-[22px] leading-[1.45] text-[var(--color-text-secondary)] max-w-[640px] mt-[var(--space-12)]">
            {subheading}
          </p>
        )}
      </div>
    </section>
  );
}
