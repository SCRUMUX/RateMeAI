/**
 * Full-screen overlay shown to soft-blocked users (1.54.0).
 *
 * Triggered by the global ``account-blocked`` ``CustomEvent`` that
 * ``request()`` in ``src/lib/api.ts`` dispatches whenever the API
 * answers 403 with ``detail.code === "account_blocked"``. Once the
 * overlay is up:
 *
 *   1. The session token is cleared from localStorage so a refresh
 *      sends the user to the regular landing instead of looping
 *      through this screen.
 *   2. All other UI is covered by a fixed-position element with
 *      ``z-[10000]`` — even modals can't appear on top.
 *
 * Visual design intentionally minimal: the user is blocked, this
 * is not the moment to show product chrome.
 */
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

const SUPPORT_EMAIL =
  (import.meta.env.VITE_SUPPORT_EMAIL ?? '').trim() || 'support@ailookstudio.ru';

interface AccountBlockedScreenProps {
  reason: string;
  onClose?: () => void;
}

export default function AccountBlockedScreen({
  reason,
  onClose,
}: AccountBlockedScreenProps) {
  const { t } = useTranslation('account');
  const handleSignOut = useCallback(() => {
    try {
      localStorage.removeItem('ailook_session_token');
    } catch { /* localStorage might be unavailable in private mode */ }
    if (onClose) onClose();
    window.location.href = '/';
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="account-blocked-title"
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/80 backdrop-blur-sm px-4"
    >
      <div className="w-full max-w-md rounded-2xl bg-[var(--color-surface,#1a1a1a)] border border-white/10 p-8 text-center shadow-2xl">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-red-500/10 text-red-400 text-3xl">
          {/* lock icon, no emoji to keep visual style consistent */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>

        <h1
          id="account-blocked-title"
          className="text-xl font-semibold text-white mb-3"
        >
          {t('blocked.title')}
        </h1>

        <p className="text-sm text-white/70 leading-relaxed mb-2">
          {t('blocked.description')}
        </p>

        {reason ? (
          <p className="text-xs text-white/50 leading-relaxed mb-6 italic">
            {t('blocked.reason', { reason })}
          </p>
        ) : (
          <div className="mb-6" />
        )}

        <a
          href={`mailto:${SUPPORT_EMAIL}`}
          className="inline-block w-full rounded-xl bg-white text-black font-medium py-2.5 px-4 hover:bg-white/90 transition mb-2"
        >
          {t('blocked.ctaSupport')}
        </a>
        <button
          type="button"
          onClick={handleSignOut}
          className="inline-block w-full rounded-xl bg-transparent text-white/70 font-medium py-2.5 px-4 border border-white/15 hover:bg-white/5 transition"
        >
          {t('blocked.ctaSignOut')}
        </button>
      </div>
    </div>
  );
}
