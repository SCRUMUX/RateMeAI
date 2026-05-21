import { createContext, useContext, useCallback, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';

type ToastType = 'success' | 'info' | 'warning';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  show: (message: string, type?: ToastType) => void;
}

const ToastCtx = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error('useToast must be inside ToastProvider');
  return ctx;
}

let nextId = 0;

const ICONS: Record<ToastType, string> = {
  success: '✓',
  info: 'ℹ',
  warning: '⚠',
};

const BG_CLASSES: Record<ToastType, string> = {
  success: 'bg-[var(--glass-surface-strong)] border-[color:color-mix(in_srgb,var(--color-success-base)_30%,transparent)]',
  info: 'bg-[var(--glass-surface-strong)] border-[color:color-mix(in_srgb,var(--color-info-base)_30%,transparent)]',
  warning: 'bg-[var(--glass-surface-strong)] border-[color:color-mix(in_srgb,var(--color-warning-base)_30%,transparent)]',
};

const ICON_CLASSES: Record<ToastType, string> = {
  success: 'text-[var(--color-success-base)]',
  info: 'text-[var(--color-info-base)]',
  warning: 'text-[var(--color-warning-base)]',
};

const AUTO_DISMISS_MS = 3500;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const show = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++nextId;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, AUTO_DISMISS_MS);
  }, []);

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      {createPortal(
        <div className="fixed top-5 left-1/2 -translate-x-1/2 z-[9999] flex flex-col items-center gap-2 pointer-events-none">
          <AnimatePresence>
            {toasts.map(t => (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: -20, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ duration: 0.25 }}
                className={`pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded-xl border backdrop-blur-md shadow-lg ${BG_CLASSES[t.type]}`}
              >
                <span className={`text-sm font-bold ${ICON_CLASSES[t.type]}`}>{ICONS[t.type]}</span>
                <span className="text-sm text-[var(--color-text-primary)]">{t.message}</span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>,
        document.body,
      )}
    </ToastCtx.Provider>
  );
}
