import { useEffect, useMemo, useState } from 'react';
import type { SocialProofFeedItem } from '../data/social-proof';

export interface TestimonialsProps {
  /**
   * Feed of social-proof items. The component shows the first
   * `VISIBLE_FEED_ITEMS` statically when motion is reduced or there
   * aren't enough entries to scroll, and otherwise slowly cycles
   * through the full feed.
   */
  feed: SocialProofFeedItem[];
  /** Block heading; defaults to "Впечатления пользователей". */
  title?: string;
  /** Optional eyebrow over the title. */
  eyebrow?: string;
  /** Ticker step interval (ms). */
  tickerIntervalMs?: number;
}

const VISIBLE_FEED_ITEMS = 3;
const FEED_ITEM_HEIGHT = 112;
const FEED_ITEM_GAP = 12;
const FEED_STEP = FEED_ITEM_HEIGHT + FEED_ITEM_GAP;
const TICKER_ANIMATION_MS = 1100;

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
 * Standalone testimonials feed extracted from the original
 * SocialProof block. The proof number/heart now live in
 * `ProofCounter` and this component is purely about the rolling
 * ticker of impressions.
 */
export default function Testimonials({
  feed,
  title = 'Впечатления пользователей',
  eyebrow,
  tickerIntervalMs = 4200,
}: TestimonialsProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [tickerIndex, setTickerIndex] = useState(0);
  const [tickerTransitionEnabled, setTickerTransitionEnabled] = useState(true);

  useEffect(() => {
    setTickerIndex(0);
    setTickerTransitionEnabled(true);
  }, [feed]);

  useEffect(() => {
    if (reducedMotion || feed.length <= VISIBLE_FEED_ITEMS) return;
    const interval = window.setInterval(() => {
      setTickerIndex((current) => current + 1);
    }, tickerIntervalMs);
    return () => window.clearInterval(interval);
  }, [feed, reducedMotion, tickerIntervalMs]);

  useEffect(() => {
    if (reducedMotion || feed.length <= VISIBLE_FEED_ITEMS || tickerIndex < feed.length) return;
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
  }, [feed.length, reducedMotion, tickerIndex]);

  const staticFeed = useMemo(() => feed.slice(0, VISIBLE_FEED_ITEMS), [feed]);
  const tickerFeed = useMemo(() => {
    if (feed.length <= VISIBLE_FEED_ITEMS) return feed;
    return [...feed, ...feed.slice(0, VISIBLE_FEED_ITEMS)];
  }, [feed]);

  if (feed.length === 0) return null;

  return (
    <section className="relative z-[2] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[88px]">
      <div className="mx-auto flex max-w-[820px] flex-col items-center gap-[var(--space-24)]">
        <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
          {eyebrow && (
            <span className="text-[12px] tablet:text-[13px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
              {eyebrow}
            </span>
          )}
          <h2 className="text-[28px] tablet:text-[40px] desktop:text-[48px] font-semibold leading-[1.1] text-[var(--color-text-primary)]">
            {title}
          </h2>
        </div>

        <div
          className="social-proof-ticker-window w-full max-w-[640px]"
          style={{
            height: `${VISIBLE_FEED_ITEMS * FEED_ITEM_HEIGHT + (VISIBLE_FEED_ITEMS - 1) * FEED_ITEM_GAP}px`,
          }}
        >
          {reducedMotion || feed.length <= VISIBLE_FEED_ITEMS ? (
            <div className="flex flex-col gap-[12px]">
              {staticFeed.map((item) => (
                <article
                  key={item.id}
                  className="social-proof-feed-item overflow-hidden"
                  style={{ height: `${FEED_ITEM_HEIGHT}px` }}
                >
                  <div className="social-proof-feed-author truncate">{item.author}</div>
                  {item.context && (
                    <div className="text-[11px] leading-[14px] text-[var(--color-text-muted)] mb-[2px] truncate">
                      {item.context}
                    </div>
                  )}
                  <p className="social-proof-feed-message line-clamp-2">{item.message}</p>
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
                  className="social-proof-feed-item overflow-hidden"
                  style={{ height: `${FEED_ITEM_HEIGHT}px` }}
                >
                  <div className="social-proof-feed-author truncate">{item.author}</div>
                  {item.context && (
                    <div className="text-[11px] leading-[14px] text-[var(--color-text-muted)] mb-[2px] truncate">
                      {item.context}
                    </div>
                  )}
                  <p className="social-proof-feed-message line-clamp-2">{item.message}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
