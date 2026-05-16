import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { startOAuth } from '../lib/auth';

export default function LinkPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation('account');
  const initialCode = params.get('code') ?? '';
  const [code, setCode] = useState(initialCode);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const c = params.get('code');
    if (c) setCode(c);
  }, [params]);

  const trimmedCode = code.trim().toUpperCase();
  const isCodeValid = trimmedCode.length >= 4;

  const handleOAuthLink = async (provider: 'yandex' | 'vk-id') => {
    if (!isCodeValid) {
      setError(t('linkPage.errors.enterCode'));
      return;
    }
    setLoading(provider);
    setError(null);
    try {
      await startOAuth(provider, undefined, trimmedCode);
    } catch {
      setError(t('linkPage.errors.linkFailed'));
      setLoading(null);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="glass-card rounded-[var(--radius-12)] p-8 max-w-md w-full flex flex-col gap-6">
        <div className="text-center">
          <h1 className="text-[22px] font-bold text-[var(--color-text-primary)]">{t('linkPage.title')}</h1>
          <p className="text-[14px] text-[var(--color-text-secondary)] mt-2">
            {t('linkPage.description')}
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-[13px] text-[var(--color-text-secondary)]">{t('linkPage.codeLabel')}</label>
          <input
            type="text"
            value={code}
            onChange={(e) => { setCode(e.target.value); setError(null); }}
            placeholder={t('linkPage.codePlaceholder')}
            maxLength={8}
            className="w-full px-4 py-3 rounded-[var(--radius-8)] text-[18px] text-center text-[var(--color-text-primary)] font-mono tracking-[0.3em] placeholder:text-[var(--color-text-muted)] outline-none uppercase bg-[var(--glass-surface-strong)] border border-[var(--glass-border-hover)]"
          />
          <p className="text-[11px] text-[var(--color-text-muted)] text-center mt-1">
            {t('linkPage.codeHint')}{' '}
            <a href="https://t.me/RateMeAI_bot" target="_blank" rel="noopener noreferrer" className="underline hover:text-[var(--color-text-secondary)]">
              @RateMeAI_bot
            </a>
            {' '}{t('linkPage.codeHintInstructions')}
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <span className="text-[13px] text-[var(--color-text-secondary)]">{t('linkPage.linkVia')}</span>

          <button
            disabled={!isCodeValid || loading !== null}
            onClick={() => handleOAuthLink('yandex')}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 text-[15px] rounded-[var(--radius-8)] font-medium transition-all disabled:opacity-40"
            style={{ background: '#FC3F1D', color: '#fff', border: 'none' }}
          >
            {loading === 'yandex' ? t('linkPage.redirecting') : t('linkPage.providers.yandex')}
          </button>

          <button
            disabled={!isCodeValid || loading !== null}
            onClick={() => handleOAuthLink('vk-id')}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 text-[15px] rounded-[var(--radius-8)] font-medium transition-all disabled:opacity-40"
            style={{ background: '#0077FF', color: '#fff', border: 'none' }}
          >
            {loading === 'vk-id' ? t('linkPage.redirecting') : t('linkPage.providers.vkId')}
          </button>
        </div>

        {error && <p className="text-[12px] text-[var(--color-danger)] text-center">{error}</p>}

        <button
          onClick={() => navigate('/', { replace: true })}
          className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
        >
          {t('linkPage.back')}
        </button>
      </div>
    </div>
  );
}
