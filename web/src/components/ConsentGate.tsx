import { useEffect, useState, useCallback, useMemo } from 'react';
import { useApp } from '../context/AppContext';

interface Props {
  children: React.ReactNode;
}

const REQUIRED_KINDS = ['data_processing', 'ai_transfer', 'age_confirmed_16'] as const;
type RequiredKind = typeof REQUIRED_KINDS[number];

const LABELS: Record<RequiredKind, string> = {
  data_processing:
    'Я даю согласие на обработку персональных данных, включая фото лица.',
  ai_transfer:
    'Я соглашаюсь на передачу фото во внешние AI-сервисы (OpenRouter, Reve и др.), в том числе за пределы РФ.',
  age_confirmed_16:
    'Мне 16 лет или больше. Я понимаю, что сервис не предназначен для лиц младше 16 лет.',
};

const HINTS: Record<RequiredKind, string> = {
  data_processing:
    'Оригинал фото не сохраняется: после обработки он удаляется. Скоры и сгенерированное изображение хранятся 72 часа.',
  ai_transfer:
    'Без этого согласия я не смогу сгенерировать новое изображение — это юридическое ограничение.',
  age_confirmed_16:
    'Требование ст. 8 GDPR и внутренних политик. При ложном подтверждении аккаунт может быть заблокирован.',
};

const PRIVACY_POLICY_URL = '/privacy';

export default function ConsentGate({ children }: Props) {
  const app = useApp();
  const [checked, setChecked] = useState<Record<RequiredKind, boolean>>({
    data_processing: false,
    ai_transfer: false,
    age_confirmed_16: false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!app.canAccessApp) return;
    if (app.consentState) return;
    void app.fetchConsents();
  }, [app.canAccessApp, app.consentState, app]);

  const missing = useMemo<RequiredKind[]>(() => {
    const state = app.consentState;
    if (!state) return REQUIRED_KINDS.slice();
    return REQUIRED_KINDS.filter(k => state.missing.includes(k));
  }, [app.consentState]);

  const allChecked = missing.every(k => checked[k]);

  const submit = useCallback(async () => {
    if (!allChecked || saving) return;
    setSaving(true);
    setError(null);
    try {
      await app.grantConsents(missing);
    } catch {
      setError('Не удалось сохранить согласие. Попробуйте ещё раз.');
    } finally {
      setSaving(false);
    }
  }, [allChecked, saving, app, missing]);

  if (!app.canAccessApp) return <>{children}</>;
  if (!app.consentState) {
    return (
      <div className="flex items-center justify-center w-full min-h-[240px] text-[var(--color-text-muted)] text-[13px]">
        Проверяем согласия…
      </div>
    );
  }
  if (missing.length === 0) return <>{children}</>;

  return (
    <div className="flex flex-col items-center gap-[var(--space-16)] w-full max-w-[560px] mx-auto py-[var(--space-24)]">
      <div className="gradient-border-card glass-card rounded-[var(--radius-16)] p-[var(--space-20)] w-full">
        <h2 className="text-[18px] tablet:text-[22px] font-semibold text-[#E6EEF8] mb-[var(--space-12)]">
          Согласия на обработку данных
        </h2>
        <p className="text-[13px] leading-[18px] text-[var(--color-text-secondary)] mb-[var(--space-16)]">
          Прежде чем загрузить фото, подтвердите все пункты. Они обязательны
          по закону. Вы можете отозвать их в любой момент в настройках профиля.
        </p>

        <div className="flex flex-col gap-[var(--space-12)]">
          {missing.map(kind => (
            <label
              key={kind}
              className="flex items-start gap-[var(--space-12)] cursor-pointer text-left"
            >
              <input
                type="checkbox"
                checked={checked[kind]}
                onChange={e =>
                  setChecked(prev => ({ ...prev, [kind]: e.target.checked }))
                }
                className="mt-[3px] w-4 h-4 accent-current"
              />
              <span className="flex flex-col gap-[var(--space-4)]">
                <span className="text-[13px] leading-[18px] text-[#E6EEF8]">
                  {LABELS[kind]}
                </span>
                <span className="text-[11px] leading-[16px] text-[var(--color-text-muted)]">
                  {HINTS[kind]}
                </span>
              </span>
            </label>
          ))}
        </div>

        <div className="mt-[var(--space-16)] flex flex-col gap-[var(--space-8)]">
          <a
            href={PRIVACY_POLICY_URL}
            target="_blank"
            rel="noreferrer"
            className="text-[12px] text-[var(--color-text-muted)] underline"
          >
            Политика обработки персональных данных
          </a>
          {error ? (
            <span className="text-[12px] text-[#FF9EAD]">{error}</span>
          ) : null}
          <button
            onClick={submit}
            disabled={!allChecked || saving}
            className="glass-btn-primary mt-[var(--space-4)] px-[var(--space-24)] py-[var(--space-12)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Сохраняем…' : 'Подтвердить и продолжить'}
          </button>
        </div>
      </div>
    </div>
  );
}
