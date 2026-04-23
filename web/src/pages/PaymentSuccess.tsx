import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AicaIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import { consumeFlowReturnPath } from '../lib/flow-resume';
import { restoreToken, startOAuth } from '../lib/auth';

export default function PaymentSuccess() {
  const { refreshBalance, session } = useApp();
  const navigate = useNavigate();
  const [targetPath] = useState(() => consumeFlowReturnPath());

  // v1.24: detect session loss right on mount. In the same-origin
  // happy path localStorage carries the token through the YooKassa
  // round-trip and AppContext restores it on boot. But when the user
  // completes payment in a different browser / Telegram webview,
  // the return URL lands in a fresh origin with no token — in that
  // case we tell them honestly and offer one-tap re-auth instead of
  // silently bouncing them into /app where the balance would look
  // like zero.
  const [sessionLost] = useState(() => restoreToken() == null);

  useEffect(() => {
    if (!sessionLost) {
      refreshBalance();
    }
  }, [refreshBalance, sessionLost]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-[var(--space-24)] px-[var(--space-24)]">
      <div className="gradient-border-card glass-card flex flex-col items-center gap-[var(--space-16)] text-center max-w-[480px] p-[var(--space-32)] rounded-[var(--radius-12)]">
        <div className="w-[72px] h-[72px] rounded-full flex items-center justify-center"
          style={{
            background: 'rgba(34, 197, 94, 0.15)',
            border: '1px solid rgba(34, 197, 94, 0.30)',
            boxShadow: '0 0 24px rgba(34, 197, 94, 0.12)',
          }}
        >
          <AicaIcon size={36} className="text-[var(--color-success-base)] -rotate-45" />
        </div>

        <h1 className="text-[32px] font-semibold leading-[1.2] text-[#E6EEF8]">
          Оплата прошла успешно!
        </h1>

        {sessionLost && !session ? (
          <>
            <p className="text-[18px] leading-[28px] text-[var(--color-text-secondary)]">
              Кредиты зачислены на ваш аккаунт. Похоже, оплата прошла
              в другом браузере — войдите снова через Telegram, чтобы
              увидеть баланс и продолжить.
            </p>
            <button
              onClick={() => { void startOAuth('yandex'); }}
              className="glass-btn-primary mt-[var(--space-8)] px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)]"
            >
              Войти снова
            </button>
          </>
        ) : (
          <>
            <p className="text-[18px] leading-[28px] text-[var(--color-text-secondary)]">
              Кредиты зачислены на ваш баланс. Теперь можно генерировать улучшенные фото.
            </p>
            <button
              onClick={() => navigate(targetPath || '/app')}
              className="glass-btn-primary mt-[var(--space-8)] px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)]"
            >
              Вернуться к приложению
            </button>
          </>
        )}
      </div>
    </div>
  );
}
