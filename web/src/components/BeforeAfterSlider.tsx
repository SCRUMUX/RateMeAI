import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

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

export default function BeforeAfterSlider({
  before,
  after,
  initial = 0.55,
  labelBefore = 'До',
  labelAfter = 'После',
}: {
  before: React.ReactNode;
  after: React.ReactNode;
  initial?: number;
  labelBefore?: string;
  labelAfter?: string;
}) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [ratio, setRatio] = useState(() => clamp01(initial));
  const containerRef = useRef<HTMLDivElement>(null);
  const id = useId();

  const setFromClientX = useCallback((clientX: number) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const next = (clientX - rect.left) / Math.max(1, rect.width);
    setRatio(clamp01(next));
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    setFromClientX(e.clientX);
  }, [setFromClientX]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!(e.buttons & 1)) return;
    setFromClientX(e.clientX);
  }, [setFromClientX]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
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
  }, []);

  const transition = useMemo(() => (prefersReducedMotion ? 'none' : 'clip-path 120ms ease-out'), [prefersReducedMotion]);

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
        style={{ clipPath: `inset(0 ${(1 - ratio) * 100}% 0 0)`, transition }}
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
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 border border-white/30 backdrop-blur flex items-center justify-center">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M7 4L3 9L7 14" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M11 4L15 9L11 14" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>

      {/* labels */}
      <div className="absolute top-[var(--space-8)] left-[var(--space-8)] glass-badge-cyan px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[var(--color-text-primary)]">
        {labelBefore}
      </div>
      <div className="absolute top-[var(--space-8)] right-[var(--space-8)] glass-badge-success px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[var(--color-text-primary)]">
        {labelAfter}
      </div>

      <span id={id} className="sr-only">{labelBefore} / {labelAfter}</span>
    </div>
  );
}

