import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import type { Testimonial } from '../data/testimonials';
import { STYLES_BY_CATEGORY } from '../data/styles';
import { useApp } from '../context/AppContext';

interface Props {
  testimonials: Testimonial[];
  initialIndex: number;
  open: boolean;
  onClose: () => void;
}

const slideVariants = {
  enter: (dir: number) => ({ x: dir > 0 ? 120 : -120, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (dir: number) => ({ x: dir > 0 ? -120 : 120, opacity: 0 }),
};

export default function ReviewModal({ testimonials, initialIndex, open, onClose }: Props) {
  const { activeCategory } = useApp();
  const [idx, setIdx] = useState(initialIndex);
  const [dir, setDir] = useState(0);

  useEffect(() => {
    if (open) setIdx(initialIndex);
  }, [open, initialIndex]);

  const testimonial = testimonials[idx];
  const style = testimonial
    ? STYLES_BY_CATEGORY[testimonial.category].find(s => s.key === testimonial.styleKey)
    : null;

  const canPrev = idx > 0;
  const canNext = idx < testimonials.length - 1;

  const goPrev = useCallback(() => {
    if (!canPrev) return;
    setDir(-1);
    setIdx(i => i - 1);
  }, [canPrev]);

  const goNext = useCallback(() => {
    if (!canNext) return;
    setDir(1);
    setIdx(i => i + 1);
  }, [canNext]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') goPrev();
      if (e.key === 'ArrowRight') goNext();
    }
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose, goPrev, goNext]);

  if (!testimonial) return null;

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
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

          {/* Nav arrows */}
          {canPrev && (
            <button
              onClick={goPrev}
              className="absolute left-[var(--space-16)] z-[10001] w-10 h-10 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          )}
          {canNext && (
            <button
              onClick={goNext}
              className="absolute right-[var(--space-16)] z-[10001] w-10 h-10 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M8 4L14 10L8 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          )}

          {/* Content (slides) */}
          <AnimatePresence mode="wait" custom={dir}>
            <motion.div
              key={testimonial.id}
              custom={dir}
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[680px] p-[var(--space-16)] tablet:p-[var(--space-32)] flex flex-col gap-[var(--space-16)] tablet:gap-[var(--space-24)]"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Close button */}
              <button
                onClick={onClose}
                className="absolute top-[var(--space-16)] right-[var(--space-16)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>

              {/* Counter */}
              <div className="absolute top-[var(--space-16)] left-1/2 -translate-x-1/2 text-[12px] text-[var(--color-text-muted)] tabular-nums">
                {idx + 1} / {testimonials.length}
              </div>

              {/* Photos row */}
              <div className="flex gap-[var(--space-12)] tablet:gap-[var(--space-24)] mt-[var(--space-8)]">
                {/* Before */}
                <div className="flex-1 flex flex-col gap-[var(--space-12)]">
                  <div className="relative rounded-[var(--radius-12)] overflow-hidden aspect-[3/4] bg-[rgba(255,255,255,0.02)]">
                    <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
                    <span className="absolute top-[var(--space-8)] left-[var(--space-8)] glass-badge-cyan px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[#E6EEF8]">
                      До
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] leading-[20px] text-[#E6EEF8] font-medium">Исходное</span>
                    <span className="flex items-center gap-1">
                      <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] tabular-nums">{testimonial.beforeScore.toFixed(2)}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full glass-progress-track overflow-hidden">
                    <div className="h-full rounded-full glass-progress-fill-muted" style={{ width: `${(testimonial.beforeScore / 10) * 100}%` }} />
                  </div>
                </div>

                {/* After */}
                <div className="flex-1 flex flex-col gap-[var(--space-12)]">
                  <div className="relative rounded-[var(--radius-12)] overflow-hidden aspect-[3/4] bg-[rgba(255,255,255,0.02)]">
                    <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50" />
                    <span className="absolute top-[var(--space-8)] left-[var(--space-8)] glass-badge-success px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[#E6EEF8]">
                      После
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] leading-[20px] text-[#E6EEF8] font-medium">{style?.name ?? 'Стиль'}</span>
                    <span className="flex items-center gap-1">
                      <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold tabular-nums">{testimonial.afterScore.toFixed(2)}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full glass-progress-track overflow-hidden">
                    <div className="h-full rounded-full glass-progress-fill" style={{ width: `${(testimonial.afterScore / 10) * 100}%` }} />
                  </div>
                </div>
              </div>

              {/* Score delta */}
              <div className="flex items-center gap-[var(--space-12)]">
                <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)] tabular-nums">{testimonial.beforeScore.toFixed(2)}</span>
                <span className="text-[14px] text-[var(--color-text-muted)]">&rarr;</span>
                <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold tabular-nums">{testimonial.afterScore.toFixed(2)}</span>
                <span className="text-[13px] leading-[18px] text-[var(--color-success-base)]">
                  (+{(testimonial.afterScore - testimonial.beforeScore).toFixed(2)})
                </span>
              </div>

              {/* User info + review */}
              <div className="flex flex-col gap-[var(--space-8)]">
                <div className="flex items-center gap-[var(--space-8)]">
                  <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">{testimonial.nickname}</span>
                  <span className="text-[13px] leading-[18px] text-[var(--color-text-muted)]">{style?.icon} {style?.name}</span>
                </div>
                <p className="text-[15px] leading-[22px] text-[var(--color-text-secondary)]">
                  {testimonial.fullReview}
                </p>
              </div>
            </motion.div>
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
