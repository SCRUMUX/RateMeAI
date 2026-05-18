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
 * Composition Safety Layer — styles that are *not* selectable for the
 * current upload's composition class. The set is composed with the
 * unlock-by-generations set above so a single ``lockedKeys`` value
 * covers both gates from the picker's point of view.
 *
 * The policy mirrors :mod:`src.services.composition_safety` on the
 * backend: ``needs_full_body=true`` styles are forbidden whenever the
 * upload is not a HALF_BODY / FULL_BODY photo (so FACE_CLOSEUP,
 * PORTRAIT, UNKNOWN all gate full-body styles).
 *
 * Style cards still render (greyed out) so the user can read the
 * description and understand what they'd unlock by uploading a wider
 * crop.
 */
export function computeCompositionLockedKeys(
  styles: readonly StyleItem[],
  compositionClass: string,
): Set<string> {
  const locked = new Set<string>();
  const cls = (compositionClass || 'unknown').toLowerCase();
  const fullBodyAllowed = cls === 'half_body' || cls === 'full_body';
  if (fullBodyAllowed) return locked;
  for (const s of styles) {
    if (s.needs_full_body) locked.add(s.key);
  }
  return locked;
}

/**
 * CSL — styles that are *risky* but not blocked (soft warning only).
 * Currently the bust-required cluster on tight head-crop uploads.
 * The wizard surfaces these as a "may look unnatural" notice but keeps
 * the card clickable.
 */
export function computeCompositionRiskyKeys(
  styles: readonly StyleItem[],
  compositionClass: string,
): Set<string> {
  const risky = new Set<string>();
  const cls = (compositionClass || 'unknown').toLowerCase();
  // Risky-torso warning only triggers on the tightest crops. Anything
  // at PORTRAIT or wider has enough bust to read well.
  if (cls !== 'face_closeup' && cls !== 'unknown') return risky;
  for (const s of styles) {
    // ``needs_full_body`` already produces a hard block — don't also
    // mark it as "risky" in addition.
    if (s.needs_full_body) continue;
    if (s.needs_torso) risky.add(s.key);
  }
  return risky;
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
