/**
 * React side of the multi-target admin (1.55.0).
 *
 * The actual ``getApiBase()`` / token plumbing lives in
 * [./api.ts](./api.ts) so non-React code (e.g. background polling
 * helpers) keeps working. This file wraps that mutable state in a
 * React context so admin pages re-render when the operator picks a
 * new target via the AdminLayout dropdown.
 *
 * The context is admin-only — non-admin pages neither mount the
 * provider nor consume the context, so the rest of the SPA keeps
 * talking to ``primary`` (the default) without changes.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import {
  ADMIN_TARGETS,
  getAdminTarget,
  type AdminTarget,
  type AdminTargetId,
} from './admin-targets';
import {
  getActiveAdminTarget,
  getTokenForTarget,
  setActiveAdminTarget,
} from './api';

interface AdminTargetContextValue {
  /** Currently active target (also propagated to api.ts). */
  current: AdminTarget;
  /** All declared targets — for rendering the switcher. */
  targets: readonly AdminTarget[];
  /** Switch to ``id``. Persists the choice in localStorage and
   *  updates api.ts so subsequent ``request()`` calls hit the new
   *  base URL with the per-target stored token. */
  setTarget: (id: AdminTargetId) => void;
  /** True if the active target has a session token in localStorage.
   *  When false, AdminLayout shows a "log in on this region" prompt
   *  instead of the page content (admin endpoints would 401). */
  hasToken: boolean;
  /** Bumped whenever ``setTarget`` runs — admin pages key their
   *  data fetches off this so caches don't leak across regions
   *  (an RU user list shouldn't appear after switching to primary). */
  switchEpoch: number;
}

const AdminTargetContext = createContext<AdminTargetContextValue | null>(null);

export function AdminTargetProvider({ children }: { children: ReactNode }) {
  const [activeId, setActiveId] = useState<AdminTargetId>(() =>
    getActiveAdminTarget(),
  );
  const [tokenSeq, setTokenSeq] = useState(0);
  const [switchEpoch, setSwitchEpoch] = useState(0);

  const current = useMemo(() => getAdminTarget(activeId), [activeId]);
  const hasToken = useMemo(
    () => Boolean(getTokenForTarget(activeId)),
    [activeId, tokenSeq],
  );

  const setTarget = useCallback(
    (id: AdminTargetId) => {
      if (id === activeId) return;
      setActiveAdminTarget(id);
      setActiveId(id);
      setSwitchEpoch((n) => n + 1);
      // Force a re-evaluation of ``hasToken`` since localStorage might
      // have changed in another tab while we were idle.
      setTokenSeq((n) => n + 1);
    },
    [activeId],
  );

  // Listen for cross-tab logout/login: another tab writing to a
  // per-target session-token key needs to reflect here so the
  // hasToken flag updates without a full reload.
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (!e.key) return;
      if (e.key.startsWith('ailook_session_token__')) {
        setTokenSeq((n) => n + 1);
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value = useMemo<AdminTargetContextValue>(
    () => ({
      current,
      targets: ADMIN_TARGETS,
      setTarget,
      hasToken,
      switchEpoch,
    }),
    [current, setTarget, hasToken, switchEpoch],
  );

  return (
    <AdminTargetContext.Provider value={value}>
      {children}
    </AdminTargetContext.Provider>
  );
}

export function useAdminTarget(): AdminTargetContextValue {
  const ctx = useContext(AdminTargetContext);
  if (!ctx) {
    throw new Error(
      'useAdminTarget must be used within <AdminTargetProvider> '
        + '(rendered inside AdminLayout).',
    );
  }
  return ctx;
}
