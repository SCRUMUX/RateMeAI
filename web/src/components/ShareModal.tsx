import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useApp } from '../context/AppContext';
import ShareButtons from './ShareButtons';

interface Props {
  open: boolean;
  onClose: () => void;
  url: string;
  text: string;
}

export default function ShareModal({ open, onClose, url, text }: Props) {
  const { activeCategory } = useApp();

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
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

          <motion.div
            className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[360px] p-[var(--space-24)] flex flex-col gap-[var(--space-16)]"
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={onClose}
              className="absolute top-[var(--space-12)] right-[var(--space-12)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>

            <h3 className="text-[18px] leading-[26px] font-semibold text-[#E6EEF8] text-center">
              Поделиться результатом
            </h3>

            <ShareButtons url={url} text={text} />

            <button
              onClick={onClose}
              className="w-full glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-8)] text-[13px] font-medium text-[var(--color-text-secondary)]"
            >
              Закрыть
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
