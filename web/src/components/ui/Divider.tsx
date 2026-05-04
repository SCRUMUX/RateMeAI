/**
 * 1.33.0 — token-driven divider primitive.
 *
 * Replaces the 5+ inline use-sites of
 * ``<div className="h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />``
 * (NavBar dropdown menu, modal sections, etc). The colour comes
 * from ``--color-divider`` so the line correctly inverts contrast
 * between dark and light themes.
 */

interface DividerProps {
  orientation?: 'horizontal' | 'vertical';
  className?: string;
}

export default function Divider({
  orientation = 'horizontal',
  className = '',
}: DividerProps) {
  const base =
    orientation === 'horizontal'
      ? 'w-full h-px'
      : 'h-full w-px';
  return (
    <div
      role="separator"
      aria-orientation={orientation}
      className={`${base} bg-[var(--color-divider)] ${className}`}
    />
  );
}
