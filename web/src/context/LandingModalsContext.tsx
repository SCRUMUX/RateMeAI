import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import PolicyModal from '../components/PolicyModal';
import SupportModal from '../components/SupportModal';
import { getPolicy } from '../data/policies';
import { findBlock, parseSupportContacts, useLandingHome } from '../lib/landing-cms';

interface LandingModalsCtx {
  openPolicy: (id: string) => void;
  openSupport: () => void;
  closeAll: () => void;
}

const LandingModalsContext = createContext<LandingModalsCtx | null>(null);

export function useLandingModals(): LandingModalsCtx {
  const ctx = useContext(LandingModalsContext);
  if (!ctx) {
    throw new Error('useLandingModals must be used within <LandingModalsProvider>');
  }
  return ctx;
}

interface ProviderProps {
  children: React.ReactNode;
}

/**
 * Singleton home for landing-level modals (policies + support).
 *
 * Why a provider instead of per-Footer state:
 * - Footer mounts on multiple landings (main, document-photo, dating-photo,
 *   resume-photo). Keeping modals here gives a single instance and lets any
 *   component (Hero CTA, NavBar, etc.) trigger them later.
 * - We honor `?policy=<id>` in the URL: routes /terms /cookie /refund /consents
 *   redirect to `/?policy=<id>` and this provider auto-opens the matching
 *   modal, then strips the query so reload doesn't re-open it.
 */
export function LandingModalsProvider({ children }: ProviderProps) {
  const [policyId, setPolicyId] = useState<string | null>(null);
  const [supportOpen, setSupportOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const openPolicy = useCallback((id: string) => {
    if (!getPolicy(id)) return;
    setPolicyId(id);
  }, []);

  const openSupport = useCallback(() => setSupportOpen(true), []);

  const closeAll = useCallback(() => {
    setPolicyId(null);
    setSupportOpen(false);
  }, []);

  // Auto-open from ?policy=<id>; always strip the query so reload doesn't
  // re-trigger (and the URL stays clean for sharing).
  useEffect(() => {
    const requested = searchParams.get('policy');
    if (!requested) return;
    if (getPolicy(requested)) {
      setPolicyId(requested);
    }
    const next = new URLSearchParams(searchParams);
    next.delete('policy');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  // Pull support contacts (telegram/email/faq) from CMS once for the
  // singleton SupportModal. CMS hook coalesces fetches across the app.
  const cmsPage = useLandingHome();
  const footerBlock = findBlock(cmsPage ?? undefined, 'footer');
  const supportContacts = useMemo(() => {
    const data = (footerBlock?.data ?? {}) as Record<string, unknown>;
    return parseSupportContacts(data.support_contacts);
  }, [footerBlock]);

  const value = useMemo<LandingModalsCtx>(
    () => ({ openPolicy, openSupport, closeAll }),
    [openPolicy, openSupport, closeAll],
  );

  return (
    <LandingModalsContext.Provider value={value}>
      {children}
      <PolicyModal
        open={policyId !== null}
        policyId={policyId}
        onClose={() => setPolicyId(null)}
      />
      <SupportModal
        open={supportOpen}
        onClose={() => setSupportOpen(false)}
        telegramUrl={supportContacts.telegram_url}
        email={supportContacts.email}
        faq={supportContacts.faq}
      />
    </LandingModalsContext.Provider>
  );
}
