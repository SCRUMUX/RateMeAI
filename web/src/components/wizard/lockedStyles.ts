import type { StyleItem } from '../../data/styles';

/**
 * Source of truth for "what's still locked for this user" — driven entirely
 * by the per-style ``unlock_after_generations`` field that ships from the
 * backend (``/api/v1/catalog/styles?schema=v2``). Pre-v1.27 there was a
 * fallback path that hashed the user id with FNV-1a to lock ~30% of styles
 * whenever the catalog hadn't been migrated yet; with the Phase-3+ catalog
 * cleanup every style ships an explicit unlock threshold (0 = open from
 * day one), so the hash-and-pick branch is gone.
 *
 * Keeping the helper module-scoped instead of inlining it into ``StepStyle``
 * because ``StylesSheet`` and the recommended-styles filter both need the
 * same locked set.
 */
export function computeLockedKeys(
  styles: readonly StyleItem[],
  taskHistoryCount: number,
): Set<string> {
  const locked = new Set<string>();
  for (const s of styles) {
    if (s.unlock_after_generations && taskHistoryCount < s.unlock_after_generations) {
      locked.add(s.key);
    }
  }
  return locked;
}

/**
 * Stable ordering: unlocked styles first (preserving the catalog's
 * curated order), locked ones at the tail. Lets ``StylesSheet`` render
 * a single flat list without losing the "best stuff at the top" feel.
 */
export function orderStylesByLock<T extends { key: string }>(
  styles: readonly T[],
  lockedKeys: Set<string>,
): T[] {
  const unlocked: T[] = [];
  const locked: T[] = [];
  for (const s of styles) {
    if (lockedKeys.has(s.key)) locked.push(s);
    else unlocked.push(s);
  }
  return [...unlocked, ...locked];
}
