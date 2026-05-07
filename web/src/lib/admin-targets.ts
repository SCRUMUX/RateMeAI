/**
 * Multi-target admin: declare which backend instances the admin
 * panel can talk to (1.55.0).
 *
 * The product runs two independent FastAPI deployments — primary on
 * Railway (used by ailookstudio.ru / vercel.app) and a RU edge VPS
 * (ru.ailookstudio.ru). Each has its OWN Postgres, its OWN Redis
 * sessions, and its OWN ``data/styles.json`` / ``data/landing_content.json``
 * on disk. So a user, a credit balance, a soft-block flag, or a CMS
 * edit only exists on the instance the request hit.
 *
 * Until 1.55 the admin panel hard-coded a single ``API_BASE`` from
 * ``VITE_API_BASE_URL``, so an operator using ailookstudio.ru/admin
 * could only ever modify primary state — RU edits silently went to
 * /dev/null. This module declares both targets so the admin layout
 * can let the operator pick.
 *
 * Defaults:
 *   - ``primary``: ``VITE_API_BASE_URL`` (or ``VITE_API_URL``) — same
 *     value the rest of the SPA uses for non-admin traffic.
 *   - ``ru``: ``VITE_ADMIN_TARGET_RU_URL``, defaulting to
 *     ``https://ru.ailookstudio.ru`` (production RU edge).
 *
 * Override either via Vercel env vars without rebuilding the
 * declaration; missing values fall back gracefully so the SPA still
 * boots in ``vite dev`` without RU configured.
 */

export type AdminTargetId = 'primary' | 'ru';

export interface AdminTarget {
  id: AdminTargetId;
  label: string;
  shortLabel: string;
  apiBase: string;
}

/** Storage key prefix for per-target session tokens — one localStorage
 *  entry per target so switching never clobbers the other token. */
export const TOKEN_STORAGE_PREFIX = 'ailook_session_token__';

/** Storage key for the currently-selected target so a refresh keeps
 *  the operator on the right instance. */
export const ACTIVE_TARGET_STORAGE_KEY = 'ailook_admin_active_target';

const _DEFAULT_PRIMARY_URL =
  import.meta.env.VITE_ADMIN_TARGET_PRIMARY_URL
  ?? import.meta.env.VITE_API_BASE_URL
  ?? import.meta.env.VITE_API_URL
  ?? '';

const _DEFAULT_RU_URL =
  import.meta.env.VITE_ADMIN_TARGET_RU_URL
  ?? 'https://ru.ailookstudio.ru';

export const ADMIN_TARGETS: readonly AdminTarget[] = [
  {
    id: 'primary',
    label: 'Primary (Railway)',
    shortLabel: 'Primary',
    apiBase: String(_DEFAULT_PRIMARY_URL).trim(),
  },
  {
    id: 'ru',
    label: 'RU (ru.ailookstudio.ru)',
    shortLabel: 'RU',
    apiBase: String(_DEFAULT_RU_URL).trim(),
  },
];

export function getAdminTarget(id: AdminTargetId): AdminTarget {
  const t = ADMIN_TARGETS.find((x) => x.id === id);
  if (!t) {
    throw new Error(`Unknown admin target: ${id}`);
  }
  return t;
}

export function tokenStorageKey(id: AdminTargetId): string {
  return `${TOKEN_STORAGE_PREFIX}${id}`;
}
