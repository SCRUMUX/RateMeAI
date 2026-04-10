import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { ToastProvider } from './components/Toast';
import Landing from './pages/Landing';
import PaymentSuccess from './pages/PaymentSuccess';
import AuthCallback from './pages/AuthCallback';

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/payment-success" element={<PaymentSuccess />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
          </Routes>
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
