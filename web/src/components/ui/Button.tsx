import type { ButtonHTMLAttributes, ReactNode } from 'react';

/**
 * 1.33.0 — token-driven Button primitive.
 *
 * Wraps the existing ``glass-btn-*`` Tailwind layers so existing
 * styling stays bit-for-bit identical at the visual layer; the
 * primitive's value is in the consistent props surface (variant /
 * size / fullWidth) and centralised disabled state. Every modal +
 * wizard surface should converge on this component instead of
 * hand-rolling `<button className="glass-btn-primary px-... py-...">`
 * blocks (currently ~30+ duplicated sites in the codebase).
 *
 * The "danger" variant uses the new `--color-danger` / `--color-
 * danger-soft` tokens introduced in 1.33.0 alongside this file.
 */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'glass';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'glass-btn-primary',
  secondary: 'glass-btn-secondary',
  ghost: 'glass-btn-ghost text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
  danger:
    'border border-[var(--color-danger-base)] text-[var(--color-danger-base)] bg-[var(--color-danger-soft)] hover:bg-[var(--color-danger-surface)] transition-colors',
  success: 'glass-btn-success',
  glass: 'glass-card hover:bg-[var(--color-surface-hover)] text-[var(--color-text-primary)] transition-colors',
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-[var(--space-12)] py-[var(--space-6)] text-[12px] leading-[16px] rounded-[var(--radius-8)]',
  md: 'px-[var(--space-16)] py-[var(--space-8)] text-[14px] leading-[20px] rounded-[var(--radius-12)]',
  lg: 'px-[var(--space-20)] py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)]',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  fullWidth,
  leftIcon,
  rightIcon,
  className = '',
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  const cls = [
    'inline-flex items-center justify-center gap-[var(--space-6)] font-medium',
    'transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer',
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    fullWidth ? 'w-full' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button type={type} disabled={disabled} className={cls} {...rest}>
      {leftIcon}
      <span className="truncate">{children}</span>
      {rightIcon}
    </button>
  );
}
