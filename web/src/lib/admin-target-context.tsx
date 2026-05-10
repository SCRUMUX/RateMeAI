/**
 * Variant B compat shim — the multi-target admin (1.55.0) is gone,
 * but ``AdminLayout`` still imports this context. We keep the same
 * surface (``current``, ``targets``, ``hasToken``, ``switchEpoch``)
 * so the layout / tabs do not need a sweep, but everything collapses
 * onto the single ``primary`` target.
 *
 * The provider exists to (a) re-render on cross-tab login/logout
 * (token change in another tab) and (b) preserve ``switchEpoch`` for
 * any admin page that still keys data fetches off it (cheap no-op).
 */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import {
  ADMIN_TARGETS,
  getAdminTarget,
  LEGACY_PRIMARY_TOKEN_KEY,
  type AdminTarget,
  type AdminTargetId,
} from './admin-targets';
import { getTokenForTarget } from './api';

interface AdminTargetContextValue {
  current: AdminTarget;
  targets: readonly AdminTarget[];
  setTarget: (id: AdminTargetId) => void;
  hasToken: boolean;
  switchEpoch: number;
}

const AdminTargetContext = createContext<AdminTargetContextValue | null>(null);

export function AdminTargetProvider({ children }: { children: ReactNode }) {
  const [tokenSeq, setTokenSeq] = useState(0);

  const current = useMemo(() => getAdminTarget('primary'), []);
  const hasToken = useMemo(
    // tokenSeq is the storage-event tick — listed in the deps so
    // hasToken re-evaluates on cross-tab login/logout.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    () => Boolean(getTokenForTarget('primary')),
    [tokenSeq],
  );

  // Listen for cross-tab logout/login.
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === LEGACY_PRIMARY_TOKEN_KEY) {
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
      setTarget: () => {
        // No-op in Variant B — only ``primary`` exists.
      },
      hasToken,
      switchEpoch: 0,
    }),
    [current, hasToken],
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
