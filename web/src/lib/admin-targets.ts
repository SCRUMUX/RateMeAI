/**
 * Variant B (CMS hub on Railway) — admin always talks to the primary
 * (Railway) backend. The RU edge no longer accepts admin writes; it
 * pulls CMS content via the signed replication channel only.
 *
 * The previous multi-target switcher (1.55.0) is gone. We keep the
 * shape (``AdminTarget``, ``getAdminTarget``) so the module surface
 * stays compatible with callers that imported types — they all
 * collapse onto a single ``primary`` target.
 */

export type AdminTargetId = 'primary';

export interface AdminTarget {
  id: AdminTargetId;
  label: string;
  shortLabel: string;
  apiBase: string;
}

/** Storage key for the session token. The pre-1.55 single-token slot
 *  is still the canonical name so the public OAuth flow and admin
 *  session share the same value. */
export const LEGACY_PRIMARY_TOKEN_KEY = 'ailook_session_token';

const _DEFAULT_PRIMARY_URL =
  import.meta.env.VITE_ADMIN_TARGET_PRIMARY_URL
  ?? import.meta.env.VITE_API_BASE_URL
  ?? import.meta.env.VITE_API_URL
  ?? '';

export const ADMIN_TARGETS: readonly AdminTarget[] = [
  {
    id: 'primary',
    label: 'Primary (Railway)',
    shortLabel: 'Primary',
    apiBase: String(_DEFAULT_PRIMARY_URL).trim(),
  },
];

export function getAdminTarget(id: AdminTargetId = 'primary'): AdminTarget {
  const t = ADMIN_TARGETS.find((x) => x.id === id);
  if (!t) {
    throw new Error(`Unknown admin target: ${id}`);
  }
  return t;
}

export function tokenStorageKey(_id: AdminTargetId = 'primary'): string {
  return LEGACY_PRIMARY_TOKEN_KEY;
}
