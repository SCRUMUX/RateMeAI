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
          </Routes>
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
