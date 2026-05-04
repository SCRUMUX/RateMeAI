import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { ToastProvider } from './components/Toast';
import Landing from './pages/Landing';
import AppPage from './pages/AppPage';
import DocumentPhotoPage from './pages/DocumentPhotoPage';
import PaymentSuccess from './pages/PaymentSuccess';
import AuthCallback from './pages/AuthCallback';
import LinkPage from './pages/LinkPage';
import PrivacyPolicy from './pages/PrivacyPolicy';

// 1.33.1 — admin pages lazy-loaded to keep them out of the main bundle.
// End-users almost never hit /admin/*, so adding ~120 kB to first paint
// for them is wasteful. Combined with manualChunks in vite.config.ts the
// admin chunk lands in a separate file fetched only on /admin/*.
const StylesAdminPage = lazy(() => import('./pages/admin/StylesAdminPage'));
const ConflictsAdminPage = lazy(() => import('./pages/admin/ConflictsAdminPage'));

function AdminFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center text-[var(--color-text-secondary)]">
      Загрузка админ-панели…
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/dokumenty" element={<DocumentPhotoPage />} />
            <Route path="/app/document-photo" element={<Navigate to="/dokumenty" replace />} />
            <Route path="/app/:scenarioSlug" element={<AppPage />} />
            <Route path="/app" element={<AppPage />} />
            <Route path="/payment-success" element={<PaymentSuccess />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/link" element={<LinkPage />} />
            <Route path="/privacy" element={<PrivacyPolicy />} />
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
          </Routes>
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
