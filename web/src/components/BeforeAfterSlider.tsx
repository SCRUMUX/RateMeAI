import { useCallback, useEffect, useId, useRef, useState } from 'react';

function clamp01(v: number): number {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
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

export interface BeforeAfterSliderProps {
  before: React.ReactNode;
  after: React.ReactNode;
  /** Initial divider position [0..1] for the interactive (drag) mode. */
  initial?: number;
  labelBefore?: string;
  labelAfter?: string;
  /**
   * When true, the slider runs a single one-shot cross-fade from
   * ``before`` to ``after`` over ``autoCycleMs``, holds the after
   * frame for ``autoHoldMs`` and stops. There is no "back-sweep" and
   * no clip-path mask — frames blend purely via opacity, like
   * beforeafterly.com. Re-mount the component (e.g. via ``key``) to
   * replay the cross-fade.
   */
  autoCycle?: boolean;
  autoCycleMs?: number;
  autoHoldMs?: number;
  /**
   * Hide the visible drag handle. Ignored in ``autoCycle`` mode
   * (autopilot has no handle by design).
   */
  hideHandle?: boolean;
  /** Hide the corner badges. */
  hideLabels?: boolean;
}

/**
 * Two presentation modes:
 *
 * 1. **Interactive (default):** drag-to-compare with a clip-path
 *    divider. Used in the marketing section, ReviewModal, etc.
 * 2. **Auto-cycle:** one-shot cross-fade ``before → after`` (no
 *    clip-path, no shutter, no reverse). Used inside testimonial
 *    cards. The carousel re-mounts each card via ``key`` so the
 *    cross-fade restarts cleanly on advance.
 */
export default function BeforeAfterSlider({
  before,
  after,
  initial = 0.55,
  labelBefore = 'До',
  labelAfter = 'После',
  autoCycle = false,
  autoCycleMs = 3000,
  autoHoldMs = 3000,
  hideHandle = false,
  hideLabels = false,
}: BeforeAfterSliderProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const id = useId();

  // Interactive divider position (only used when !autoCycle).
  const [ratio, setRatio] = useState(() => clamp01(initial));
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-cycle cross-fade progress (0..1). Starts at 0 (only `before`
  // visible), animates to 1 (only `after` visible) and stays there.
  const [fade, setFade] = useState(() => (autoCycle ? 0 : 1));

  const setFromClientX = useCallback((clientX: number) => {
    if (autoCycle) return;
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const next = (clientX - rect.left) / Math.max(1, rect.width);
    setRatio(clamp01(next));
  }, [autoCycle]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (autoCycle) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    setFromClientX(e.clientX);
  }, [autoCycle, setFromClientX]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (autoCycle) return;
    if (!(e.buttons & 1)) return;
    setFromClientX(e.clientX);
  }, [autoCycle, setFromClientX]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (autoCycle) return;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setRatio((r) => clamp01(r - 0.04));
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setRatio((r) => clamp01(r + 0.04));
    } else if (e.key === 'Home') {
      e.preventDefault();
      setRatio(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      setRatio(1);
    }
  }, [autoCycle]);

  // One-shot cross-fade: `fade` 0→1 over `autoCycleMs`, then hold at
  // 1 for `autoHoldMs` and stop. No reverse, no loop. Component is
  // re-mounted by the carousel via `key={item.id}` to replay.
  useEffect(() => {
    if (!autoCycle) return;
    if (prefersReducedMotion) {
      setFade(1);
      return;
    }

    let rafId = 0;
    let cancelled = false;
    const start = performance.now();
    const sweepMs = Math.max(200, autoCycleMs);
    const totalMs = sweepMs + Math.max(0, autoHoldMs);

    const tick = (now: number) => {
      if (cancelled) return;
      const elapsed = now - start;
      if (elapsed >= sweepMs) {
        setFade(1);
        if (elapsed < totalMs) {
          rafId = requestAnimationFrame(tick);
        }
        return;
      }
      // Linear progression — feels like a clean dissolve. Easing
      // here makes the transition feel slow at the start which we
      // don't want; "beforeafterly"-style is uniform.
      setFade(elapsed / sweepMs);
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
    };
  }, [autoCycle, autoCycleMs, autoHoldMs, prefersReducedMotion]);

  const showDivider = !autoCycle;

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full rounded-[var(--radius-12)] overflow-hidden bg-[var(--color-surface-2)] select-none touch-none"
      aria-labelledby={id}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
    >
      {/* Before frame — full size baseline, always rendered. */}
      <div className="absolute inset-0">
        {before}
      </div>

      {/* After frame — full size on top, blended via opacity in
          autoCycle mode and via clip-path in interactive mode. */}
      <div
        className="absolute inset-0"
        style={
          autoCycle
            ? {
                opacity: fade,
                transition: prefersReducedMotion ? 'none' : 'opacity 80ms linear',
              }
            : {
                clipPath: `inset(0 ${(1 - ratio) * 100}% 0 0)`,
                transition: prefersReducedMotion ? 'none' : 'clip-path 120ms ease-out',
              }
        }
      >
        <div className="absolute inset-0">
          {after}
        </div>
      </div>

      {/* Draggable divider — interactive mode only. */}
      {showDivider && (
        <div
          role="slider"
          aria-labelledby={id}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(ratio * 100)}
          tabIndex={0}
          onKeyDown={handleKeyDown}
          className="absolute inset-y-0 cursor-ew-resize focus:outline-none"
          style={{ left: `${ratio * 100}%`, transform: 'translateX(-50%)' }}
        >
          <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-white/70" />
          {!hideHandle && (
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 border border-white/30 backdrop-blur flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M7 4L3 9L7 14" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M11 4L15 9L11 14" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          )}
        </div>
      )}

      {/* Corner badges — hidden by default in autoCycle mode (the
          carousel disables them). */}
      {!hideLabels && (
        <>
          <div className="absolute top-[var(--space-8)] left-[var(--space-8)] glass-badge-cyan px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[var(--color-text-primary)]">
            {labelBefore}
          </div>
          <div className="absolute top-[var(--space-8)] right-[var(--space-8)] glass-badge-success px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[var(--color-text-primary)]">
            {labelAfter}
          </div>
        </>
      )}

      <span id={id} className="sr-only">{labelBefore} / {labelAfter}</span>
    </div>
  );
}
