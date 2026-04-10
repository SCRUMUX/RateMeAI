import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { startOAuth } from '../lib/auth';
import * as api from '../lib/api';

export default function LinkPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
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
      setError('Введите код привязки');
      return;
    }
    setLoading(provider);
    setError(null);
    try {
      await startOAuth(provider, undefined, trimmedCode);
    } catch {
      setError('Не удалось начать привязку.');
      setLoading(null);
    }
  };

  const handleSendOtp = async () => {
    const digits = phoneInput.replace(/\D/g, '');
    if (digits.length < 10) {
      setError('Введите корректный номер телефона');
      return;
    }
    setLoading('phone');
    setError(null);
    try {
      await api.phoneSendCode(digits);
      setOtpSent(true);
    } catch {
      setError('Не удалось отправить код.');
    } finally {
      setLoading(null);
    }
  };

  const handlePhoneVerify = async () => {
    if (!isCodeValid) {
      setError('Введите код привязки');
      return;
    }
    const digits = phoneInput.replace(/\D/g, '');
    setLoading('phone-verify');
    setError(null);
    try {
      const res = await api.phoneVerify(digits, otpCode, trimmedCode);
      if (res.session_token) {
        setSuccess(true);
        setTimeout(() => navigate('/', { replace: true }), 2000);
      }
    } catch (e) {
      setError(e instanceof api.ApiError ? e.body : 'Неверный код.');
    } finally {
      setLoading(null);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="glass-card rounded-[var(--radius-12)] p-8 max-w-md w-full text-center">
          <p className="text-lg font-medium text-[#4ADE80]">
            Аккаунт успешно привязан!
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="glass-card rounded-[var(--radius-12)] p-8 max-w-md w-full flex flex-col gap-6">
        <div className="text-center">
          <h1 className="text-[22px] font-bold text-[#E6EEF8]">Привязка аккаунта</h1>
          <p className="text-[14px] text-[var(--color-text-secondary)] mt-2">
            Введите код из бота или веб-приложения, затем выберите способ привязки
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-[13px] text-[var(--color-text-secondary)]">Код привязки</label>
          <input
            type="text"
            value={code}
            onChange={(e) => { setCode(e.target.value); setError(null); }}
            placeholder="ABC123"
            maxLength={8}
            className="w-full px-4 py-3 rounded-[var(--radius-8)] text-[18px] text-center text-[#E6EEF8] font-mono tracking-[0.3em] placeholder:text-[var(--color-text-muted)] outline-none uppercase"
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }}
          />
          <p className="text-[11px] text-[var(--color-text-muted)] text-center mt-1">
            Откуда взять код? В Telegram-боте{' '}
            <a href="https://t.me/RateMeAIBot" target="_blank" rel="noopener noreferrer" className="underline hover:text-[var(--color-text-secondary)]">
              @RateMeAIBot
            </a>
            {' '}нажми &laquo;Привязать аккаунт&raquo; &rarr; &laquo;Хочу войти на сайт через бот&raquo;
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <span className="text-[13px] text-[var(--color-text-secondary)]">Привязать через:</span>

          <button
            disabled={!isCodeValid || loading !== null}
            onClick={() => handleOAuthLink('yandex')}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 text-[15px] rounded-[var(--radius-8)] font-medium transition-all disabled:opacity-40"
            style={{ background: '#FC3F1D', color: '#fff', border: 'none' }}
          >
            {loading === 'yandex' ? 'Перенаправление...' : 'Яндекс'}
          </button>

          <button
            disabled={!isCodeValid || loading !== null}
            onClick={() => handleOAuthLink('vk-id')}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 text-[15px] rounded-[var(--radius-8)] font-medium transition-all disabled:opacity-40"
            style={{ background: '#0077FF', color: '#fff', border: 'none' }}
          >
            {loading === 'vk-id' ? 'Перенаправление...' : 'ВКонтакте'}
          </button>

          <div className="flex flex-col gap-2">
            {!otpSent ? (
              <div className="flex gap-2">
                <input
                  type="tel"
                  value={phoneInput}
                  onChange={(e) => { setPhoneInput(e.target.value); setError(null); }}
                  placeholder="+7 (999) 123-45-67"
                  className="flex-1 px-3 py-3 rounded-[var(--radius-8)] text-[14px] text-[#E6EEF8] placeholder:text-[var(--color-text-muted)] outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.10)' }}
                />
                <button
                  disabled={loading !== null}
                  onClick={handleSendOtp}
                  className="px-4 py-3 text-[14px] rounded-[var(--radius-8)] font-medium shrink-0 disabled:opacity-50"
                  style={{ background: '#4ADE80', color: '#000', border: 'none' }}
                >
                  {loading === 'phone' ? '...' : 'Код'}
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  value={otpCode}
                  onChange={(e) => { setOtpCode(e.target.value); setError(null); }}
                  placeholder="Код из SMS"
                  maxLength={6}
                  className="flex-1 px-3 py-3 rounded-[var(--radius-8)] text-[14px] text-[#E6EEF8] placeholder:text-[var(--color-text-muted)] outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.10)' }}
                />
                <button
                  disabled={!isCodeValid || loading !== null || otpCode.length < 4}
                  onClick={handlePhoneVerify}
                  className="px-5 py-3 text-[14px] rounded-[var(--radius-8)] font-medium shrink-0 disabled:opacity-50"
                  style={{ background: '#4ADE80', color: '#000', border: 'none' }}
                >
                  {loading === 'phone-verify' ? '...' : 'OK'}
                </button>
              </div>
            )}
          </div>
        </div>

        {error && <p className="text-[12px] text-[#FF4D6A] text-center">{error}</p>}

        <button
          onClick={() => navigate('/', { replace: true })}
          className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
        >
          Вернуться на главную
        </button>
      </div>
    </div>
  );
}
