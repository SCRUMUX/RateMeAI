import type { ResolvedSlots } from '../lib/api';

interface Props {
  /**
   * The slot map written by the v3 prompt pipeline. ``undefined``
   * or ``null`` means "not a v3 generation" (legacy history entry,
   * v2 fallback path) — the component renders nothing in that case.
   */
  slots: ResolvedSlots | null | undefined;
  /**
   * Section heading. ``StepGenerate`` wants the long form ("Что
   * выбрано в этой генерации"); ``StorageModal`` runs out of room
   * inside the small card and prefers a shorter caption. Defaults
   * to the long form so the rare careless caller still gets a sane
   * label.
   */
  caption?: string;
  /**
   * Visual variant. ``inline`` is the dense layout used inside a
   * gallery card (no caption, smaller chips, max 4 channels);
   * ``stacked`` is the full-width layout used under the live
   * generation result (caption + all rolled channels).
   */
  variant?: 'inline' | 'stacked';
  /** Cap each chip's value text. Long phrases get ellipsis. */
  maxValueChars?: number;
  /** Optional className applied to the outer wrapper. */
  className?: string;
}

// Channel display order is fixed across both variants so the user
// builds a stable mental model: trigger first (read-only headline),
// then time-bound channels (lighting / weather / time / season),
// then identity-adjacent (clothing).
const ORDER: Array<{ key: keyof ResolvedSlots; label: string }> = [
  { key: 'trigger', label: 'Триггер' },
  { key: 'lighting', label: 'Свет' },
  { key: 'weather', label: 'Погода' },
  { key: 'time_of_day', label: 'Время суток' },
  { key: 'season', label: 'Сезон' },
  { key: 'clothing', label: 'Одежда' },
];

const INLINE_MAX_ITEMS = 4;

function ellipsise(value: string, max: number): string {
  if (max <= 0 || value.length <= max) return value;
  return `${value.slice(0, max).trimEnd()}…`;
}

/**
 * Renders the «Что выбрано в этой генерации» badge strip for a v3
 * resolved-slots map. Used by ``StepGenerate`` (under the live
 * result) and ``StorageModal`` (under each gallery card) so both
 * surfaces show the same data with the same vocabulary.
 *
 * Returns ``null`` when there is nothing to render — callers do not
 * need to guard.
 */
export default function ResolvedSlotsBadges({
  slots,
  caption = 'Что выбрано в этой генерации',
  variant = 'stacked',
  maxValueChars,
  className,
}: Props) {
  if (!slots) return null;

  const items = ORDER
    .map(({ key, label }) => {
      const raw = slots[key];
      const value = typeof raw === 'string' ? raw.trim() : '';
      return { key, label, value };
    })
    .filter(it => it.value.length > 0);

  if (items.length === 0) return null;

  const inline = variant === 'inline';
  const visible = inline ? items.slice(0, INLINE_MAX_ITEMS) : items;
  const overflow = items.length - visible.length;
  const maxLen = maxValueChars ?? (inline ? 18 : 32);

  if (inline) {
    return (
      <div
        className={`flex flex-wrap items-center gap-[var(--space-4)] ${className ?? ''}`}
        title={items.map(it => `${it.label}: ${it.value}`).join(' · ')}
      >
        {visible.map(it => (
          <span
            key={it.key}
            className="inline-flex items-center gap-[3px] px-[var(--space-8)] py-[1px] rounded-[var(--radius-pill)] text-[10px] leading-[14px] font-medium glass-btn-ghost text-[var(--color-text-secondary)] max-w-full"
          >
            <span className="text-[var(--color-text-muted)] truncate">{it.label}:</span>{' '}
            <span className="text-[var(--color-text-primary)] truncate">{ellipsise(it.value, maxLen)}</span>
          </span>
        ))}
        {overflow > 0 && (
          <span className="text-[10px] leading-[14px] text-[var(--color-text-muted)]">
            +{overflow}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col items-center gap-[var(--space-4)] px-[var(--space-8)] ${className ?? ''}`}
    >
      {caption && (
        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] uppercase tracking-wider">
          {caption}
        </span>
      )}
      <div className="flex flex-wrap items-center justify-center gap-[var(--space-4)] max-w-[520px]">
        {visible.map(it => (
          <span
            key={it.key}
            className="px-[var(--space-10)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[16px] font-medium glass-btn-ghost text-[var(--color-text-secondary)]"
            title={it.value}
          >
            <span className="text-[var(--color-text-muted)]">{it.label}:</span>{' '}
            <span className="text-[var(--color-text-primary)]">{ellipsise(it.value, maxLen)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
