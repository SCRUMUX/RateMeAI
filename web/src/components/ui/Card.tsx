import type { HTMLAttributes, ReactNode } from 'react';

/**
 * 1.33.0 — token-driven Card primitive.
 *
 * Three visual variants:
 *   * ``glass``   — current ``glass-card`` Tailwind layer
 *     (translucent, the default for floating surfaces).
 *   * ``solid``   — opaque ``bg-surface-1`` with elevation-2; for
 *     popovers / dropdowns where a translucent surface stacked on
 *     another translucent surface would muddy the contrast (this is
 *     the lesson from 1.31.1 where the StyleSettingsModal dropdown
 *     was unreadable through nested backdrop-filters).
 *   * ``gradient-border`` — adds the ``gradient-border-card`` class
 *     used on AuthModal / AppPage hero CTAs.
 */

type Variant = 'glass' | 'solid' | 'gradient-border';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  children?: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  glass: 'glass-card',
  solid: 'bg-[var(--color-surface-1)] shadow-[var(--effect-elevation-2)] border border-[var(--color-border-base)]',
  'gradient-border': 'gradient-border-card glass-card',
};

export default function Card({
  variant = 'glass',
  className = '',
  children,
  ...rest
}: CardProps) {
  const cls = [
    'rounded-[var(--radius-16)]',
    VARIANT_CLASSES[variant],
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
