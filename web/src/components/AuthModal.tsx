import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';

interface Props {
  open: boolean;
  onClose: () => void;
  onAuth: (phone: string) => Promise<void>;
  onOAuth?: (provider: 'yandex' | 'vk-id') => Promise<void>;
}

export default function AuthModal({ open, onClose, onAuth, onOAuth }: Props) {
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const digits = phone.replace(/\D/g, '');
    if (!digits) { setError('Введите номер телефона'); return; }
    if (digits.length < 10) { setError('Некорректный номер телефона'); return; }
    setLoading(true);
    setError(null);
    try {
      await onAuth(digits);
    } catch {
      setError('Вход по телефону пока недоступен. Войдите через Яндекс или ВКонтакте.');
    } finally {
      setLoading(false);
    }
  }, [phone, onAuth]);

  const handleOAuth = useCallback(async (provider: 'yandex' | 'vk-id') => {
    if (!onOAuth) return;
    setOauthLoading(provider);
    setError(null);
    try {
      await onOAuth(provider);
    } catch {
      setError('Не удалось начать авторизацию.');
      setOauthLoading(null);
    }
  }, [onOAuth]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[9999] flex items-center justify-center p-[var(--space-24)]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

          <motion.div
            className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[420px] p-[var(--space-32)] flex flex-col gap-[var(--space-24)]"
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close */}
            <button
              onClick={onClose}
              className="absolute top-[var(--space-16)] right-[var(--space-16)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>

            {/* Header */}
            <div className="flex flex-col gap-[var(--space-8)] text-center">
              <h3 className="text-[24px] leading-[32px] font-semibold text-[#E6EEF8]">Получить доступ</h3>
              <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">
                Войдите через аккаунт Яндекс или ВКонтакте, чтобы увидеть результаты анализа
              </p>
            </div>

            {/* OAuth buttons */}
            <div className="flex flex-col gap-[var(--space-12)]">
              <button
                type="button"
                disabled={oauthLoading !== null}
                onClick={() => handleOAuth('yandex')}
                className="w-full flex items-center justify-center gap-3 px-[var(--space-20)] py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium transition-all disabled:opacity-50"
                style={{
                  background: '#FC3F1D',
                  color: '#fff',
                  border: 'none',
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M13.32 7.666h-.924c-1.694 0-2.585.858-2.585 2.123 0 1.43.616 2.1 1.881 2.959l1.045.704-3.003 4.548H7.5l2.739-4.064c-1.584-1.155-2.475-2.31-2.475-4.147 0-2.354 1.628-3.97 4.643-3.97h2.926V18H13.32V7.666z" fill="currentColor"/>
                </svg>
                {oauthLoading === 'yandex' ? 'Перенаправление...' : 'Войти через Яндекс'}
              </button>

              <button
                type="button"
                disabled={oauthLoading !== null}
                onClick={() => handleOAuth('vk-id')}
                className="w-full flex items-center justify-center gap-3 px-[var(--space-20)] py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium transition-all disabled:opacity-50"
                style={{
                  background: '#0077FF',
                  color: '#fff',
                  border: 'none',
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M12.77 17.29c-5.47 0-8.59-3.74-8.72-9.96h2.74c.09 4.56 2.1 6.49 3.69 6.89V7.33h2.58v3.93c1.57-.17 3.22-1.97 3.78-3.93h2.58c-.43 2.41-2.24 4.21-3.52 4.94 1.28.59 3.33 2.16 4.11 5.02h-2.84c-.61-1.9-2.13-3.37-4.11-3.57v3.57h-.29z" fill="currentColor"/>
                </svg>
                {oauthLoading === 'vk-id' ? 'Перенаправление...' : 'Войти через ВКонтакте'}
              </button>
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
              <span className="text-[12px] text-[var(--color-text-muted)]">или</span>
              <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-[var(--space-16)]">
              <div className="flex flex-col gap-[var(--space-8)]">
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => { setPhone(e.target.value); setError(null); }}
                  placeholder="+7 (999) 123-45-67"
                  className="w-full px-[var(--space-16)] py-[var(--space-12)] rounded-[var(--radius-12)] text-[15px] leading-[22px] text-[#E6EEF8] placeholder:text-[var(--color-text-muted)] outline-none transition-all"
                  style={{
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.10)',
                    backdropFilter: 'blur(8px)',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.4)'; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.10)'; }}
                />
                {error && (
                  <span className="text-[12px] leading-[16px] text-[#FF4D6A]">{error}</span>
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="glass-btn-primary w-full px-[var(--space-20)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)] disabled:opacity-50"
              >
                {loading ? 'Подключение...' : 'Продолжить с телефоном'}
              </button>
            </form>

            <p className="text-[12px] leading-[16px] text-[var(--color-text-muted)] text-center">
              Нажимая кнопку входа, вы соглашаетесь с условиями использования
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
