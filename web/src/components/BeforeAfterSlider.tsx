import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

function clamp01(v: number): number {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
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
  /** Initial divider position [0..1]. Ignored when `autoCycle` is on. */
  initial?: number;
  labelBefore?: string;
  labelAfter?: string;
  /**
   * Enables an automatic divider sweep that travels from
   * ``autoFrom`` → ``autoTo`` over ``autoCycleMs``, holds for
   * ``autoHoldMs``, and then loops. User dragging pauses the
   * autopilot for ``autoResumeDelayMs`` after the last interaction.
   */
  autoCycle?: boolean;
  autoCycleMs?: number;
  autoHoldMs?: number;
  autoFrom?: number;
  autoTo?: number;
  autoResumeDelayMs?: number;
  /** Hide the visible drag handle but keep the divider line. */
  hideHandle?: boolean;
  /** Hide the corner badges. */
  hideLabels?: boolean;
}

/**
 * Drag-to-compare slider with an optional auto-cycling divider.
 *
 * The "after" image is rendered full-size and clipped via
 * ``clip-path`` so neither side is squished (no horizontal scaling).
 * In autoCycle mode we also fade the after layer's opacity in
 * lock-step with the divider position to give the transition a soft
 * cross-fade feel on top of the hard clip mask. User drag/keyboard
 * input always wins and pauses the autopilot.
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
  autoFrom = 0.05,
  autoTo = 0.95,
  autoResumeDelayMs = 1500,
  hideHandle = false,
  hideLabels = false,
}: BeforeAfterSliderProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [ratio, setRatio] = useState(() => clamp01(autoCycle ? autoFrom : initial));
  const containerRef = useRef<HTMLDivElement>(null);
  const id = useId();

  // Pause-token for the auto loop. We don't disable the loop by
  // unmounting the effect (that would lose accumulated phase) — we
  // freeze it via a ref so user drag is instant.
  const pausedUntilRef = useRef<number>(0);

  const setFromClientX = useCallback((clientX: number) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const next = (clientX - rect.left) / Math.max(1, rect.width);
    setRatio(clamp01(next));
  }, []);

  const pauseAutopilot = useCallback(() => {
    if (!autoCycle) return;
    pausedUntilRef.current = performance.now() + autoResumeDelayMs;
  }, [autoCycle, autoResumeDelayMs]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    pauseAutopilot();
    setFromClientX(e.clientX);
  }, [pauseAutopilot, setFromClientX]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!(e.buttons & 1)) return;
    pauseAutopilot();
    setFromClientX(e.clientX);
  }, [pauseAutopilot, setFromClientX]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      pauseAutopilot();
      setRatio((r) => clamp01(r - 0.04));
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      pauseAutopilot();
      setRatio((r) => clamp01(r + 0.04));
    } else if (e.key === 'Home') {
      e.preventDefault();
      pauseAutopilot();
      setRatio(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      pauseAutopilot();
      setRatio(1);
    }
  }, [pauseAutopilot]);

  // Auto-cycle loop using rAF so we can express the schedule
  // (sweep → hold → reverse → hold) precisely. Phase advances only
  // when the autopilot isn't paused; user drag wins instantly because
  // ratio is owned by setRatio above.
  useEffect(() => {
    if (!autoCycle || prefersReducedMotion) return;
    let rafId = 0;
    let lastFrame = performance.now();
    let phase = 0; // 0..1 sweep, 1..2 hold-after, 2..3 reverse, 3..4 hold-before
    let direction: 'forward' | 'reverse' = 'forward';
    const sweepMs = Math.max(200, autoCycleMs);
    const holdMs = Math.max(0, autoHoldMs);

    const tick = (now: number) => {
      const dt = now - lastFrame;
      lastFrame = now;
      if (now >= pausedUntilRef.current) {
        if (direction === 'forward') {
          if (phase < 1) {
            phase = Math.min(1, phase + dt / sweepMs);
          } else if (phase < 2) {
            phase = Math.min(2, phase + dt / Math.max(1, holdMs));
            if (phase >= 2) {
              direction = 'reverse';
              phase = 0;
            }
          }
        } else {
          if (phase < 1) {
            phase = Math.min(1, phase + dt / sweepMs);
          } else if (phase < 2) {
            phase = Math.min(2, phase + dt / Math.max(1, holdMs));
            if (phase >= 2) {
              direction = 'forward';
              phase = 0;
            }
          }
        }

        const eased = phase < 1 ? easeInOutCubic(phase) : 1;
        const next = direction === 'forward'
          ? autoFrom + (autoTo - autoFrom) * eased
          : autoTo - (autoTo - autoFrom) * eased;
        setRatio(clamp01(next));
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [autoCycle, autoCycleMs, autoHoldMs, autoFrom, autoTo, prefersReducedMotion]);

  // For the "soft cross-fade on top of the hard clip" effect — the
  // after layer's opacity follows ratio (mostly opaque, lightly
  // damped) so the transition reads as a dissolve as well as a slide.
  const afterOpacity = useMemo(() => {
    if (!autoCycle) return 1;
    return 0.55 + 0.45 * ratio;
  }, [autoCycle, ratio]);

  const transition = useMemo(() => {
    if (prefersReducedMotion) return 'none';
    return autoCycle ? 'clip-path 80ms linear, opacity 80ms linear' : 'clip-path 120ms ease-out';
  }, [autoCycle, prefersReducedMotion]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full rounded-[var(--radius-12)] overflow-hidden bg-[var(--glass-surface-soft)] select-none touch-none"
      aria-labelledby={id}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
    >
      {/* Before image — full size baseline */}
      <div className="absolute inset-0">
        {before}
      </div>

      {/* After image — same full-size, but clipped to ratio% on the right.
          Using clip-path keeps the inner content's intrinsic size (no horizontal squish). */}
      <div
        className="absolute inset-0"
        style={{
          clipPath: `inset(0 ${(1 - ratio) * 100}% 0 0)`,
          opacity: afterOpacity,
          transition,
        }}
      >
        <div className="absolute inset-0">
          {after}
        </div>
      </div>

      {/* Draggable divider + handle */}
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
        {/* divider */}
        <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-white/70" />
        {/* handle */}
        {!hideHandle && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 border border-white/30 backdrop-blur flex items-center justify-center">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M7 4L3 9L7 14" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M11 4L15 9L11 14" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        )}
      </div>

      {/* labels */}
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
