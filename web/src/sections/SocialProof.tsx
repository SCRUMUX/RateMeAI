import { useEffect, useMemo, useState } from 'react';
import type { SocialProofPreset } from '../data/social-proof';

interface SocialProofProps {
  preset: SocialProofPreset;
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

const VISIBLE_FEED_ITEMS = 3;
const FEED_ITEM_HEIGHT = 112;
const FEED_ITEM_GAP = 12;
const FEED_STEP = FEED_ITEM_HEIGHT + FEED_ITEM_GAP;
const TICKER_ANIMATION_MS = 1100;

export default function SocialProof({ preset }: SocialProofProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [count, setCount] = useState(preset.baseCount);
  const [tickerIndex, setTickerIndex] = useState(0);
  const [tickerTransitionEnabled, setTickerTransitionEnabled] = useState(true);

  useEffect(() => {
    setCount(preset.baseCount);
    setTickerIndex(0);
    setTickerTransitionEnabled(true);
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
    if (reducedMotion || preset.feed.length <= VISIBLE_FEED_ITEMS) return;

    const interval = window.setInterval(() => {
      setTickerIndex((current) => current + 1);
    }, preset.tickerIntervalMs);

    return () => window.clearInterval(interval);
  }, [preset, reducedMotion]);

  useEffect(() => {
    if (reducedMotion || preset.feed.length <= VISIBLE_FEED_ITEMS || tickerIndex < preset.feed.length) return;

    const resetTimeout = window.setTimeout(() => {
      setTickerTransitionEnabled(false);
      setTickerIndex(0);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setTickerTransitionEnabled(true);
        });
      });
    }, TICKER_ANIMATION_MS);

    return () => window.clearTimeout(resetTimeout);
  }, [preset.feed.length, reducedMotion, tickerIndex]);

  const staticFeed = useMemo(
    () => preset.feed.slice(0, VISIBLE_FEED_ITEMS),
    [preset.feed],
  );

  const tickerFeed = useMemo(() => {
    if (preset.feed.length <= VISIBLE_FEED_ITEMS) return preset.feed;
    return [...preset.feed, ...preset.feed.slice(0, VISIBLE_FEED_ITEMS)];
  }, [preset.feed]);

  return (
    <section className="relative z-[2] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[88px]">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-[var(--space-24)] tablet:gap-[var(--space-32)] desktop:grid-cols-[minmax(0,1fr)_minmax(380px,0.92fr)] desktop:items-start">
        <div className="flex flex-col justify-center gap-[var(--space-16)] py-[var(--space-8)]">
          <h2 className="text-[32px] tablet:text-[46px] desktop:text-[56px] font-semibold leading-[1.02] text-[#E6EEF8]">
            {preset.title}
          </h2>
          <div className="social-proof-counter-value text-[56px] tablet:text-[88px] desktop:text-[112px] font-semibold leading-none text-[var(--color-brand-primary)] tabular-nums">
            {formatCounter(count)}
          </div>
        </div>

        <div className="flex flex-col gap-[var(--space-16)]">
          <h3 className="text-[22px] tablet:text-[28px] font-semibold leading-[1.1] text-[#E6EEF8]">
            Впечатления пользователей
          </h3>

          <div
            className="social-proof-ticker-window"
            style={{ height: `${VISIBLE_FEED_ITEMS * FEED_ITEM_HEIGHT + (VISIBLE_FEED_ITEMS - 1) * FEED_ITEM_GAP}px` }}
          >
            {reducedMotion || preset.feed.length <= VISIBLE_FEED_ITEMS ? (
              <div className="flex flex-col gap-[12px]">
                {staticFeed.map((item) => (
                  <article key={item.id} className="social-proof-feed-item">
                    <div className="social-proof-feed-author">{item.author}</div>
                    <p className="social-proof-feed-message">{item.message}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div
                className="social-proof-ticker-track"
                style={{
                  gap: `${FEED_ITEM_GAP}px`,
                  transform: `translateY(-${tickerIndex * FEED_STEP}px)`,
                  transitionDuration: tickerTransitionEnabled ? `${TICKER_ANIMATION_MS}ms` : '0ms',
                }}
              >
                {tickerFeed.map((item, index) => (
                  <article
                    key={`${item.id}-${index}`}
                    className="social-proof-feed-item"
                    style={{ minHeight: `${FEED_ITEM_HEIGHT}px` }}
                  >
                    <div className="social-proof-feed-author">{item.author}</div>
                    <p className="social-proof-feed-message">{item.message}</p>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
