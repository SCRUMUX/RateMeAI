import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigationType } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AppProvider } from './context/AppContext';
import { LandingModalsProvider } from './context/LandingModalsContext';
import { ToastProvider } from './components/Toast';
import { useReveal } from './lib/useReveal';
import AccountBlockedScreen from './components/AccountBlockedScreen';
import Landing from './pages/Landing';
import AppPage from './pages/AppPage';
import DocumentPhotoPage from './pages/DocumentPhotoPage';
import DatingPhotoPage from './pages/DatingPhotoPage';
import ResumePhotoPage from './pages/ResumePhotoPage';
import VisaPage from './pages/VisaPage';
import PaymentSuccess from './pages/PaymentSuccess';
import AuthCallback from './pages/AuthCallback';
import LinkPage from './pages/LinkPage';
import PrivacyPolicy from './pages/PrivacyPolicy';
import NotFound from './pages/NotFound';

// 1.33.1 — admin pages lazy-loaded to keep them out of the main bundle.
// End-users almost never hit /admin/*, so adding ~120 kB to first paint
// for them is wasteful. Combined with manualChunks in vite.config.ts the
// admin chunk lands in a separate file fetched only on /admin/*.
const StylesAdminPage = lazy(() => import('./pages/admin/StylesAdminPage'));
const ConflictsAdminPage = lazy(() => import('./pages/admin/ConflictsAdminPage'));
const LandingAdminPage = lazy(() => import('./pages/admin/LandingAdminPage'));
const UsersAdminPage = lazy(() => import('./pages/admin/UsersAdminPage'));

function AdminFallback() {
  const { t } = useTranslation('common');
  return (
    <div className="min-h-screen flex items-center justify-center text-[var(--color-text-secondary)]">
      {t('loading.admin')}
    </div>
  );
}

/**
 * 1.50.7 — Force scroll-to-top on every router PUSH/REPLACE so that
 * cross-page navigation (e.g. Footer "Products" links) reliably lands
 * at the top of the next page's hero. POP (browser back/forward) is
 * left untouched so the browser's native scroll-restoration keeps
 * working.
 */
function ScrollToTop() {
  const { pathname } = useLocation();
  const navType = useNavigationType();
  useEffect(() => {
    if (navType !== 'POP') {
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' as ScrollBehavior });
    }
  }, [pathname, navType]);
  return null;
}

/**
 * 1.54.0 — Global ``account-blocked`` listener.
 *
 * ``request()`` in ``src/lib/api.ts`` dispatches this event whenever the
 * API answers 403 with ``{code: "account_blocked"}``. We render the
 * full-screen overlay above all routes so the blocked user can't
 * interact with anything else.
 */
function useAccountBlockedListener(): {
  blocked: boolean;
  reason: string;
  clear: () => void;
} {
  const [blocked, setBlocked] = useState(false);
  const [reason, setReason] = useState('');
  useEffect(() => {
    const handler = (event: Event) => {
      const ce = event as CustomEvent<{ reason?: string }>;
      setReason(ce.detail?.reason ?? '');
      setBlocked(true);
    };
    window.addEventListener('account-blocked', handler);
    return () => window.removeEventListener('account-blocked', handler);
  }, []);
  return { blocked, reason, clear: () => setBlocked(false) };
}

export default function App() {
  // 1.50.3: scroll-reveal singleton — один IntersectionObserver
  // активирует .reveal/.reveal-stagger ноды по всему приложению.
  useReveal();
  const { blocked, reason, clear } = useAccountBlockedListener();

  return (
    <BrowserRouter>
      <ScrollToTop />
      <ToastProvider>
        <AppProvider>
          <LandingModalsProvider>
            {blocked && (
              <AccountBlockedScreen reason={reason} onClose={clear} />
            )}
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/dokumenty" element={<DocumentPhotoPage />} />
              <Route path="/app/document-photo" element={<Navigate to="/dokumenty" replace />} />
              <Route path="/znakomstva" element={<DatingPhotoPage />} />
              <Route path="/app/dating-photo" element={<Navigate to="/znakomstva" replace />} />
              <Route path="/rezume" element={<ResumePhotoPage />} />
              <Route path="/app/resume-photo" element={<Navigate to="/rezume" replace />} />
              <Route path="/visa/:country" element={<VisaPage />} />
              <Route path="/app/:scenarioSlug" element={<AppPage />} />
              <Route path="/app" element={<AppPage />} />
              <Route path="/payment-success" element={<PaymentSuccess />} />
              <Route path="/auth/callback" element={<AuthCallback />} />
              <Route path="/link" element={<LinkPage />} />
              <Route path="/privacy" element={<PrivacyPolicy />} />
              {/* Policy redirect-routes — open the corresponding modal on the
                  home page via ?policy=<id>; LandingModalsProvider strips the
                  query after triggering. */}
              <Route path="/terms" element={<Navigate to="/?policy=terms" replace />} />
              <Route path="/cookie" element={<Navigate to="/?policy=cookie" replace />} />
              <Route path="/refund" element={<Navigate to="/?policy=refund" replace />} />
              <Route path="/consents" element={<Navigate to="/?policy=consents" replace />} />
              <Route
                path="/admin/styles"
                element={
                  <Suspense fallback={<AdminFallback />}>
                    <StylesAdminPage />
                  </Suspense>
                }
              />
              <Route
                path="/admin/conflicts"
                element={
                  <Suspense fallback={<AdminFallback />}>
                    <ConflictsAdminPage />
                  </Suspense>
                }
              />
              <Route
                path="/admin/landing"
                element={
                  <Suspense fallback={<AdminFallback />}>
                    <LandingAdminPage />
                  </Suspense>
                }
              />
              <Route
                path="/admin/users"
                element={
                  <Suspense fallback={<AdminFallback />}>
                    <UsersAdminPage />
                  </Suspense>
                }
              />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </LandingModalsProvider>
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
