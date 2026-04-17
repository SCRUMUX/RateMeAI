import type { StyleItem } from '../../data/styles';

const ANON_SEED_KEY = 'lookstudio:anon-seed';
export const UNLOCK_AFTER_GENERATIONS = 5;

// FNV-1a 32-bit hash — стабильный, быстрый, детерминированный.
function fnv1a(str: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function getUserLockSeed(userId: string | null | undefined): string {
  if (userId) return `u:${userId}`;
  if (typeof window === 'undefined') return 'anon:server';
  try {
    let seed = window.localStorage.getItem(ANON_SEED_KEY);
    if (!seed) {
      seed = (window.crypto && 'randomUUID' in window.crypto)
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem(ANON_SEED_KEY, seed);
    }
    return `a:${seed}`;
  } catch {
    return 'anon:fallback';
  }
}

/**
 * Детерминированно выбирает ~30% стилей из списка как локнутые.
 * Один и тот же `userSeed` + `styles` всегда даёт один и тот же Set,
 * поэтому при повторных визитах пользователь видит те же локнутые стили.
 * При `taskHistoryCount >= UNLOCK_AFTER_GENERATIONS` всё разлочено.
 */
export function computeLockedKeys(
  styles: readonly StyleItem[],
  userSeed: string,
  taskHistoryCount: number,
): Set<string> {
  if (taskHistoryCount >= UNLOCK_AFTER_GENERATIONS) return new Set();
  if (styles.length === 0) return new Set();

  const scored = styles.map((s) => ({
    key: s.key,
    rank: fnv1a(`${userSeed}:${s.key}`),
  }));
  scored.sort((a, b) => a.rank - b.rank);
  const lockedCount = Math.floor(styles.length * 0.3);
  const locked = new Set<string>();
  for (let i = 0; i < lockedCount; i++) locked.add(scored[i].key);
  return locked;
}

/**
 * Сортирует стили так, чтобы доступные шли первыми (в исходном порядке),
 * а локнутые — в самом конце.
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
