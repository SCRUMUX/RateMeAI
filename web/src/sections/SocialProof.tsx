import { useEffect, useMemo, useRef, useState } from 'react';
import type { SocialProofPreset } from '../data/social-proof';

interface SocialProofProps {
  preset: SocialProofPreset;
}

interface HeartBurst {
  id: number;
  x: number;
  y: number;
  size: number;
  durationMs: number;
  delayMs: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;

    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setPrefersReducedMotion(media.matches);

    update();
    media.addEventListener('change', update);

    return () => media.removeEventListener('change', update);
  }, []);

  return prefersReducedMotion;
}

function formatCounter(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}

export default function SocialProof({ preset }: SocialProofProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [count, setCount] = useState(preset.baseCount);
  const [heartBursts, setHeartBursts] = useState<HeartBurst[]>([]);
  const [tickerIndex, setTickerIndex] = useState(0);
  const nextHeartIdRef = useRef(0);

  const safeVisibleCount = clamp(preset.feedVisibleCount, 1, Math.max(preset.feed.length, 1));

  useEffect(() => {
    setCount(preset.baseCount);
    setTickerIndex(0);
    setHeartBursts([]);
  }, [preset]);

  useEffect(() => {
    if (reducedMotion) return;

    let cancelled = false;
    let timeoutId: number | undefined;

    const scheduleTick = () => {
      const delay = randomInt(preset.counter.minDelayMs, preset.counter.maxDelayMs);
      timeoutId = window.setTimeout(() => {
        if (cancelled) return;

        const burstTriggered = Math.random() < preset.counter.burstChance;
        const increment = burstTriggered
          ? randomInt(2, Math.max(2, preset.counter.maxBurstSize))
          : 1;

        setCount((current) => current + increment);

        if (Math.random() < preset.counter.heartChance) {
          const heartsCount = increment > 1 ? randomInt(2, 4) : randomInt(1, 3);
          const createdAt = Date.now();

          const newBursts = Array.from({ length: heartsCount }, (_, index) => ({
            id: createdAt + nextHeartIdRef.current++ + index,
            x: randomInt(12, 88),
            y: randomInt(20, 78),
            size: randomInt(14, 24),
            durationMs: randomInt(1700, 2500),
            delayMs: randomInt(0, 180),
          }));

          setHeartBursts((current) => [...current, ...newBursts]);

          const cleanupDelay = Math.max(...newBursts.map((item) => item.durationMs + item.delayMs)) + 350;
          window.setTimeout(() => {
            setHeartBursts((current) => current.filter((item) => !newBursts.some((burst) => burst.id === item.id)));
          }, cleanupDelay);
        }

        scheduleTick();
      }, delay);
    };

    scheduleTick();

    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [preset, reducedMotion]);

  useEffect(() => {
    if (preset.feed.length <= safeVisibleCount) return;

    const interval = window.setInterval(() => {
      setTickerIndex((current) => (current + 1) % preset.feed.length);
    }, reducedMotion ? Math.max(3600, preset.tickerIntervalMs) : preset.tickerIntervalMs);

    return () => window.clearInterval(interval);
  }, [preset, reducedMotion, safeVisibleCount]);

  const visibleFeed = useMemo(() => {
    if (preset.feed.length === 0) return [];
    if (preset.feed.length <= safeVisibleCount) return preset.feed;

    return Array.from({ length: safeVisibleCount }, (_, offset) => {
      const index = (tickerIndex + offset) % preset.feed.length;
      return preset.feed[index];
    });
  }, [preset.feed, safeVisibleCount, tickerIndex]);

  return (
    <section className="relative z-[2] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[88px]">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-[var(--space-16)] tablet:gap-[var(--space-24)] desktop:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)] desktop:items-stretch">
        <div className="gradient-border-card glass-card relative overflow-hidden rounded-[var(--radius-12)] p-[var(--space-20)] tablet:p-[var(--space-24)] desktop:p-[var(--space-32)]">
          <div className="grain-overlay opacity-40" />

          <div className="relative flex h-full flex-col gap-[var(--space-20)]">
            <div className="flex flex-wrap items-center gap-[var(--space-8)]">
              <span
                className="gradient-border-item inline-flex items-center rounded-[var(--radius-pill)] px-[var(--space-10)] py-[var(--space-6)] text-[12px] font-medium leading-[16px] text-[var(--color-brand-primary)]"
                style={{ '--gb-color': 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.28)' } as React.CSSProperties}
              >
                {preset.eyebrow}
              </span>
              {preset.highlights.map((item) => (
                <span
                  key={item}
                  className="inline-flex items-center rounded-[var(--radius-pill)] border border-white/10 bg-white/5 px-[var(--space-10)] py-[var(--space-6)] text-[12px] leading-[16px] text-[var(--color-text-secondary)]"
                >
                  {item}
                </span>
              ))}
            </div>

            <div className="flex flex-col gap-[var(--space-10)]">
              <p className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                Доверие растет в фоне
              </p>
              <h2 className="text-[28px] tablet:text-[40px] desktop:text-[48px] font-semibold leading-[1.05] text-[#E6EEF8]">
                {preset.title}
              </h2>
              <p className="max-w-[640px] text-[15px] tablet:text-[18px] leading-[22px] tablet:leading-[28px] text-[var(--color-text-secondary)]">
                {preset.description}
              </p>
            </div>

            <div className="grid gap-[var(--space-12)] tablet:grid-cols-[minmax(0,1fr)_auto] tablet:items-end">
              <div className="gradient-border-item relative overflow-hidden rounded-[var(--radius-12)] bg-[rgba(255,255,255,0.04)] px-[var(--space-16)] py-[var(--space-16)] tablet:px-[var(--space-20)] tablet:py-[var(--space-20)]">
                <div className="social-proof-counter-glow" />
                <div className="relative flex flex-col gap-[var(--space-8)]">
                  <div className="social-proof-hearts pointer-events-none absolute inset-0">
                    {heartBursts.map((burst) => (
                      <span
                        key={burst.id}
                        className={`social-proof-heart ${reducedMotion ? 'social-proof-heart-static' : ''}`}
                        style={{
                          left: `${burst.x}%`,
                          top: `${burst.y}%`,
                          fontSize: `${burst.size}px`,
                          animationDuration: `${burst.durationMs}ms`,
                          animationDelay: `${burst.delayMs}ms`,
                        }}
                      >
                        ❤
                      </span>
                    ))}
                  </div>

                  <span className="text-[12px] tablet:text-[13px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                    Сейчас в блоке
                  </span>
                  <div className="flex flex-wrap items-end gap-x-[var(--space-12)] gap-y-[var(--space-6)]">
                    <span className="social-proof-counter-value text-[42px] tablet:text-[64px] font-semibold leading-none text-[#E6EEF8] tabular-nums">
                      {formatCounter(count)}
                    </span>
                    <span className="max-w-[280px] pb-[4px] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)]">
                      {preset.statLabel}
                    </span>
                  </div>
                  <p className="max-w-[560px] text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-muted)]">
                    {preset.statSubLabel}
                  </p>
                </div>
              </div>

              <div className="flex flex-row tablet:flex-col gap-[var(--space-8)] tablet:min-w-[180px]">
                <div className="gradient-border-item flex-1 rounded-[var(--radius-12)] px-[var(--space-12)] py-[var(--space-12)] text-center tablet:text-left">
                  <div className="text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">Ритм</div>
                  <div className="mt-[6px] text-[15px] font-medium text-[#E6EEF8]">Неровный, живой</div>
                </div>
                <div className="gradient-border-item flex-1 rounded-[var(--radius-12)] px-[var(--space-12)] py-[var(--space-12)] text-center tablet:text-left">
                  <div className="text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">Лента</div>
                  <div className="mt-[6px] text-[15px] font-medium text-[#E6EEF8]">{preset.feed.length} сообщений по кругу</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="gradient-border-card glass-card relative overflow-hidden rounded-[var(--radius-12)] p-[var(--space-20)] tablet:p-[var(--space-24)] desktop:p-[var(--space-28)]">
          <div className="social-proof-ticker-mask" />
          <div className="relative flex h-full flex-col gap-[var(--space-16)]">
            <div className="flex items-center justify-between gap-[var(--space-12)]">
              <div>
                <p className="text-[13px] tablet:text-[14px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                  {preset.tickerLabel}
                </p>
                <h3 className="mt-[6px] text-[22px] tablet:text-[26px] font-semibold leading-[1.1] text-[#E6EEF8]">
                  Живая лента впечатлений
                </h3>
              </div>
              <span className="rounded-[var(--radius-pill)] border border-[rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.28)] bg-[rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.10)] px-[var(--space-10)] py-[var(--space-6)] text-[12px] font-medium leading-[16px] text-[var(--color-brand-primary)]">
                online
              </span>
            </div>

            <div className="relative flex flex-1 flex-col gap-[var(--space-10)]">
              {visibleFeed.map((item, index) => (
                <article
                  key={`${item.id}-${tickerIndex}-${index}`}
                  className={`social-proof-feed-item gradient-border-item rounded-[var(--radius-12)] px-[var(--space-14)] py-[var(--space-14)] ${
                    reducedMotion ? '' : 'social-proof-feed-item-animated'
                  }`}
                  style={{ '--gb-color': index === 0 ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.24)' : 'rgba(255,255,255,0.10)' } as React.CSSProperties}
                >
                  <div className="flex items-start justify-between gap-[var(--space-12)]">
                    <div className="min-w-0">
                      <div className="text-[14px] font-medium leading-[20px] text-[#E6EEF8]">
                        {item.author}
                      </div>
                      <div className="mt-[2px] text-[12px] leading-[16px] text-[var(--color-text-muted)]">
                        {item.context}
                      </div>
                    </div>
                    <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)]">
                      {index === 0 ? '●' : '○'}
                    </span>
                  </div>
                  <p className="mt-[var(--space-10)] text-[14px] tablet:text-[15px] leading-[20px] tablet:leading-[22px] text-[var(--color-text-secondary)]">
                    {item.message}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
