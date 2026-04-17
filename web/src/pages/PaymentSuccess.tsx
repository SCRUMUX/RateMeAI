import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AicaIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import { consumeFlowReturnPath } from '../lib/flow-resume';

export default function PaymentSuccess() {
  const { refreshBalance } = useApp();
  const navigate = useNavigate();
  const [targetPath] = useState(() => consumeFlowReturnPath());

  useEffect(() => {
    refreshBalance();
  }, [refreshBalance]);

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

        <p className="text-[18px] leading-[28px] text-[var(--color-text-secondary)]">
          Кредиты зачислены на ваш баланс. Теперь можно генерировать улучшенные фото.
        </p>

        <button
          onClick={() => navigate(targetPath || '/app')}
          className="glass-btn-primary mt-[var(--space-8)] px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)]"
        >
          Вернуться к приложению
        </button>
      </div>
    </div>
  );
}
