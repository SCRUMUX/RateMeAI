import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';

interface Props {
  open: boolean;
  onClose: () => void;
  onOAuth?: (provider: 'yandex' | 'vk-id') => Promise<void>;
  required?: boolean;
}

export default function AuthModal({ open, onClose, onOAuth, required }: Props) {
  const { activeCategory } = useApp();
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !required) onClose();
    }
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose, required]);

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
          data-category={activeCategory}
          className="fixed inset-0 z-[9999] flex items-center justify-center p-[var(--space-24)]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={required ? undefined : onClose} />

          <motion.div
            className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[420px] p-[var(--space-32)] flex flex-col gap-[var(--space-24)]"
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            {!required && (
              <button
                onClick={onClose}
                className="absolute top-[var(--space-16)] right-[var(--space-16)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            )}

            {/* Header */}
            <div className="flex flex-col gap-[var(--space-8)] text-center">
              <h3 className="text-[24px] leading-[32px] font-semibold text-[#E6EEF8]">
                {required ? 'Авторизация' : 'Получить доступ'}
              </h3>
              <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">
                {required
                  ? 'В соответствии с законодательством, для использования приложения необходима авторизация'
                  : 'Войдите через аккаунт Яндекс или ВКонтакте, чтобы увидеть результаты анализа'}
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

            {error && (
              <span className="text-[12px] leading-[16px] text-[#FF4D6A] text-center">{error}</span>
            )}

            <p className="text-[12px] leading-[16px] text-[var(--color-text-muted)] text-center">
              Нажимая кнопку входа, вы соглашаетесь с условиями использования
            </p>

            {required && (
              <Link
                to="/"
                className="flex items-center justify-center gap-[var(--space-6)] text-[14px] leading-[20px] text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors no-underline"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Вернуться на главную
              </Link>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
