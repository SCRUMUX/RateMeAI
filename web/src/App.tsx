import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { ToastProvider } from './components/Toast';
import Landing from './pages/Landing';
import AppPage from './pages/AppPage';
import PaymentSuccess from './pages/PaymentSuccess';
import AuthCallback from './pages/AuthCallback';
import LinkPage from './pages/LinkPage';

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/app" element={<AppPage />} />
            <Route path="/payment-success" element={<PaymentSuccess />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/link" element={<LinkPage />} />
          </Routes>
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
