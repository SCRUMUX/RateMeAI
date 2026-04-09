import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { setToken } from '../lib/auth';
import { useApp } from '../context/AppContext';

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithToken } = useApp();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const token = params.get('token');
    if (token) {
      setToken(token);
      loginWithToken(token)
        .catch(() => {})
        .finally(() => navigate('/', { replace: true }));
    } else {
      navigate('/', { replace: true });
    }
  }, [params, navigate, loginWithToken]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-[var(--color-text-secondary)] text-lg">Авторизация...</p>
    </div>
  );
}
