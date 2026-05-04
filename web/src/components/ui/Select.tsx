import { useEffect, useRef, useState } from 'react';

/**
 * 1.33.0 — token-driven Select primitive.
 *
 * Extracted from the inline ``Dropdown`` introduced in
 * ``StyleSettingsModal`` (1.31.0). Why custom over a native
 * ``<select>``? On Windows the native menu picks up OS chrome
 * (white opaque list, system fonts) that ignores ``data-theme`` —
 * users on dark theme saw a glaring white dropdown panel. This
 * component reuses the existing token vocabulary so the popover
 * inverts cleanly between dark/light themes.
 *
 * The popover surface uses ``bg-[var(--color-surface-1)]`` +
 * ``shadow-[var(--effect-elevation-2)]`` (NOT the translucent
 * ``glass-card``) — nested backdrop-filters were the cause of the
 * 1.31.0 transparency complaint where the dropdown was illegible
 * over the modal scrim.
 */

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
}

export default function Select({
  value,
  options,
  onChange,
  placeholder = 'Выберите...',
  ariaLabel,
  disabled,
  className = '',
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleMouseDown(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleMouseDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const currentLabel =
    options.find((o) => o.value === value)?.label ?? placeholder;

  return (
    <div ref={containerRef} className={`relative w-full ${className}`}>
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-base)] rounded-[var(--radius-8)] px-3 py-2 text-[14px] text-[var(--color-text-primary)] text-left flex items-center justify-between gap-[var(--space-8)] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
      >
        <span
          className={`truncate ${value ? '' : 'text-[var(--color-text-muted)]'}`}
        >
          {currentLabel}
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
          className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+4px)] z-10 bg-[var(--color-surface-1)] shadow-[var(--effect-elevation-2)] rounded-[var(--radius-8)] border border-[var(--color-border-base)] p-[var(--space-4)] flex flex-col gap-[2px] max-h-[240px] overflow-y-auto"
        >
          {options.map((opt) => {
            const active = opt.value === value;
            return (
              <button
                key={opt.value || '__placeholder__'}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`w-full text-left px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-8)] text-[14px] leading-[20px] transition-colors cursor-pointer ${
                  active
                    ? 'bg-[var(--color-surface-3)] text-[var(--color-text-primary)]'
                    : 'text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
