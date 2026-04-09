import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { setToken } from '../lib/auth';
import { useApp } from '../context/AppContext';

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithToken } = useApp();
  const handled = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const token = params.get('token');
    const userId = params.get('user_id') ?? '';
    const oauthError = params.get('error');

    if (oauthError) {
      setError(`Ошибка авторизации: ${params.get('error_description') || oauthError}`);
      return;
    }

    if (token) {
      setToken(token);
      loginWithToken(token, userId)
        .catch(() => setError('Не удалось завершить авторизацию. Попробуйте снова.'))
        .then(() => navigate('/', { replace: true }));
    } else {
      setError('Токен авторизации не получен. Попробуйте войти снова.');
    }
  }, [params, navigate, loginWithToken]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="glass-card rounded-[var(--radius-12)] p-8 max-w-md w-full flex flex-col gap-4 text-center">
          <p className="text-[#FF4D6A] text-lg font-medium">{error}</p>
          <button
            onClick={() => navigate('/', { replace: true })}
            className="glass-btn-primary px-6 py-3 rounded-[var(--radius-12)] text-[15px]"
          >
            Вернуться на главную
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-[var(--color-text-secondary)] text-lg">Авторизация...</p>
    </div>
  );
}
