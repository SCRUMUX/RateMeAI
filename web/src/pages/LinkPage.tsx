import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { startOAuth, setToken } from '../lib/auth';
import * as api from '../lib/api';
import { useApp } from '../context/AppContext';
import { humanizeApiError } from '../lib/sanitize';

export default function LinkPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithToken } = useApp();
  const { t } = useTranslation('account');
  const initialCode = params.get('code') ?? '';
  const [code, setCode] = useState(initialCode);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [phoneInput, setPhoneInput] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');

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

  const handleSendOtp = async () => {
    const digits = phoneInput.replace(/\D/g, '');
    if (digits.length < 10) {
      setError(t('linkPage.errors.phoneInvalid'));
      return;
    }
    setLoading('phone');
    setError(null);
    try {
      await api.phoneSendCode(digits);
      setOtpSent(true);
    } catch {
      setError(t('linkPage.errors.otpFailed'));
    } finally {
      setLoading(null);
    }
  };

  const handlePhoneVerify = async () => {
    if (!isCodeValid) {
      setError(t('linkPage.errors.enterCode'));
      return;
    }
    const digits = phoneInput.replace(/\D/g, '');
    setLoading('phone-verify');
    setError(null);
    try {
      const res = await api.phoneVerify(digits, otpCode, trimmedCode);
      if (res.session_token) {
        setToken(res.session_token);
        await loginWithToken(res.session_token, res.user_id ?? '', 'phone');
        setSuccess(true);
        setTimeout(() => navigate('/', { replace: true }), 2000);
      }
    } catch (e) {
      setError(humanizeApiError(e, t('linkPage.errors.otpVerifyFailed')));
    } finally {
      setLoading(null);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="glass-card rounded-[var(--radius-12)] p-8 max-w-md w-full text-center">
          <p className="text-lg font-medium text-[var(--color-success-base)]">
            {t('linkPage.successTitle')}
          </p>
        </div>
      </div>
    );
  }

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

          <div className="flex flex-col gap-2">
            {!otpSent ? (
              <div className="flex gap-2">
                <input
                  type="tel"
                  value={phoneInput}
                  onChange={(e) => { setPhoneInput(e.target.value); setError(null); }}
                  placeholder={t('linkPage.phonePlaceholder')}
                  className="flex-1 px-3 py-3 rounded-[var(--radius-8)] text-[14px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] outline-none bg-[var(--glass-surface)] border border-[var(--glass-border)]"
                />
                <button
                  disabled={loading !== null}
                  onClick={handleSendOtp}
                  className="px-4 py-3 text-[14px] rounded-[var(--radius-8)] font-medium shrink-0 disabled:opacity-50"
                  style={{ background: 'var(--color-success-base)', color: '#000', border: 'none' }}
                >
                  {loading === 'phone' ? '...' : t('linkPage.ctaSendCode')}
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  value={otpCode}
                  onChange={(e) => { setOtpCode(e.target.value); setError(null); }}
                  placeholder={t('linkPage.otpPlaceholder')}
                  maxLength={6}
                  className="flex-1 px-3 py-3 rounded-[var(--radius-8)] text-[14px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] outline-none bg-[var(--glass-surface)] border border-[var(--glass-border)]"
                />
                <button
                  disabled={!isCodeValid || loading !== null || otpCode.length < 4}
                  onClick={handlePhoneVerify}
                  className="px-5 py-3 text-[14px] rounded-[var(--radius-8)] font-medium shrink-0 disabled:opacity-50"
                  style={{ background: 'var(--color-success-base)', color: '#000', border: 'none' }}
                >
                  {loading === 'phone-verify' ? '...' : t('linkPage.ctaVerify')}
                </button>
              </div>
            )}
          </div>
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
