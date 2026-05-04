import type { ReactNode } from 'react';

/**
 * 1.33.0 — token-driven Field primitive: label + control + helper /
 * error text in one consistent vertical stack.
 *
 * Replaces the hand-rolled
 * ``<label>label</label><input/><span>error</span>`` patterns
 * sprinkled across AuthModal / StorageModal / StyleSettingsModal.
 * The component is layout-only — the actual control is whatever the
 * caller renders into ``children`` (a native input, a Select, a
 * textarea). This keeps the migration cheap (no behaviour changes)
 * while standardising spacing, typography and error tone.
 */

interface FieldProps {
  label?: ReactNode;
  helper?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}

export default function Field({
  label,
  helper,
  error,
  required,
  htmlFor,
  children,
  className = '',
}: FieldProps) {
  return (
    <div className={`flex flex-col gap-[var(--space-6)] ${className}`}>
      {label && (
        <label
          htmlFor={htmlFor}
          className="text-[12px] leading-[16px] font-medium text-[var(--color-text-secondary)]"
        >
          {label}
          {required ? <span className="text-[var(--color-danger-base)]"> *</span> : null}
        </label>
      )}
      {children}
      {error ? (
        <span className="text-[12px] leading-[16px] text-[var(--color-danger-base)]">
          {error}
        </span>
      ) : helper ? (
        <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)]">
          {helper}
        </span>
      ) : null}
    </div>
  );
}
