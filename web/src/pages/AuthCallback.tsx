import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { setToken } from '../lib/auth';
import { useApp } from '../context/AppContext';
import { consumeOAuthReturnPath } from '../lib/flow-resume';

function isSafeReturnPath(path: string | null | undefined): path is string {
  if (!path) return false;
  if (!path.startsWith('/')) return false;
  if (path.startsWith('//') || path.startsWith('/\\')) return false;
  return true;
}

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithToken } = useApp();
  const handled = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation('errors');

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const token = params.get('token');
    const userId = params.get('user_id') ?? '';
    const provider = params.get('provider') ?? '';
    const oauthError = params.get('error');
    const queryReturnPath = params.get('return_path');

    if (oauthError) {
      const detail = params.get('error_description') || oauthError;
      setError(t('auth.oauth_error_prefix', { detail }));
      return;
    }

    if (token) {
      setToken(token);
      loginWithToken(token, userId, provider)
        .then(() => {
          // Priority: server-provided ``return_path`` (works across
          // origins) → sessionStorage fallback (same-origin only) → ``/``.
          const path = isSafeReturnPath(queryReturnPath)
            ? queryReturnPath
            : consumeOAuthReturnPath('/');
          navigate(path, { replace: true });
        })
        .catch(() => setError(t('auth.callback_failed')));
    } else {
      setError(t('auth.no_token'));
    }
  }, [params, navigate, loginWithToken, t]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="glass-card rounded-[var(--radius-12)] p-8 max-w-md w-full flex flex-col gap-4 text-center">
          <p className="text-[var(--color-danger)] text-lg font-medium">{error}</p>
          <button
            onClick={() => navigate('/', { replace: true })}
            className="glass-btn-primary px-6 py-3 rounded-[var(--radius-12)] text-[15px]"
          >
            {t('auth.back_home')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-[var(--color-text-secondary)] text-lg">{t('auth.loading')}</p>
    </div>
  );
}
