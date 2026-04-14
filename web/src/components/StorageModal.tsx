import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import type { TaskHistoryItem } from '../lib/api';
import { createShare } from '../lib/api';
import { normalizeImageUrl } from '../lib/image-url';
import { STYLES_BY_CATEGORY } from '../data/styles';
import { useApp } from '../context/AppContext';
import ProgressBar from './wizard/ProgressBar';
import ShareButtons from './ShareButtons';

const STYLE_LOOKUP: Record<string, { name: string; icon: string }> = {};
for (const styles of Object.values(STYLES_BY_CATEGORY)) {
  for (const s of styles) {
    STYLE_LOOKUP[s.key] = { name: s.name, icon: s.icon };
  }
}

interface Props {
  items: TaskHistoryItem[];
  open: boolean;
  onClose: () => void;
  onImprove?: (imageUrl: string) => void;
}

const slideVariants = {
  enter: (dir: number) => ({ x: dir > 0 ? 120 : -120, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (dir: number) => ({ x: dir > 0 ? -120 : 120, opacity: 0 }),
};

const PARAM_LABELS: Record<string, string> = {
  warmth: 'Теплота',
  presence: 'Уверенность',
  appeal: 'Привлекательность',
  trust: 'Доверие',
  competence: 'Компетентность',
  hireability: 'Найм',
  authenticity: 'Аутентичность',
};

export default function StorageModal({ items, open, onClose, onImprove }: Props) {
  const { activeCategory } = useApp();
  const [idx, setIdx] = useState(0);
  const [dir, setDir] = useState(0);
  const [viewTab, setViewTab] = useState<'result' | 'original'>('result');
  const [shareData, setShareData] = useState<{ url: string; text: string } | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);
  const [imgErrors, setImgErrors] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (open) { setIdx(0); setViewTab('result'); }
  }, [open]);

  const item = items[idx];
  const styleInfo = item ? STYLE_LOOKUP[item.style] : null;
  const canPrev = idx > 0;
  const canNext = idx < items.length - 1;

  const goPrev = useCallback(() => {
    if (!canPrev) return;
    setDir(-1);
    setIdx(i => i - 1);
    setViewTab('result');
    setShareData(null);
  }, [canPrev]);

  const goNext = useCallback(() => {
    if (!canNext) return;
    setDir(1);
    setIdx(i => i + 1);
    setViewTab('result');
    setShareData(null);
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

  async function handleDownload() {
    if (!item?.generated_image_url) return;
    setDownloadError(false);
    const url = normalizeImageUrl(item.generated_image_url);
    const downloadUrl = url.includes('?') ? `${url}&download=1` : `${url}?download=1`;
    try {
      const res = await fetch(downloadUrl, { credentials: 'omit' });
      if (!res.ok) {
        setDownloadError(true);
        return;
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `generation-${item.task_id.slice(0, 8)}.jpg`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      setDownloadError(true);
    }
  }

  async function handleShowShare() {
    if (!item?.task_id || shareLoading) return;
    if (shareData) { setShareData(null); return; }
    setShareLoading(true);
    try {
      const res = await createShare(item.task_id);
      setShareData({ url: res.deep_link, text: res.caption });
    } catch { /* ignore */ }
    setShareLoading(false);
  }

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

          {items.length === 0 ? (
            <div
              className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[440px] p-[var(--space-32)] flex flex-col items-center gap-[var(--space-20)] text-center"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={onClose}
                className="absolute top-[var(--space-16)] right-[var(--space-16)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
              <p className="text-[16px] text-[#E6EEF8] font-medium mt-[var(--space-8)]">Пока нет генераций</p>
              <p className="text-[14px] text-[var(--color-text-secondary)]">Загрузите фото и выберите стиль, чтобы начать</p>
              <button
                onClick={onClose}
                className="glass-btn-primary rounded-[var(--radius-12)] px-[var(--space-24)] py-[var(--space-10)] text-[14px] font-semibold text-white"
              >
                Улучшить фото
              </button>
            </div>
          ) : item && (
            <AnimatePresence mode="wait" custom={dir}>
              <motion.div
                key={item.task_id}
                custom={dir}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[480px] max-h-[90vh] overflow-y-auto p-[var(--space-16)] tablet:p-[var(--space-32)] flex flex-col gap-[var(--space-16)] tablet:gap-[var(--space-24)]"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={onClose}
                  className="absolute top-[var(--space-16)] right-[var(--space-16)] w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>

                <div className="absolute top-[var(--space-16)] left-1/2 -translate-x-1/2 text-[12px] text-[var(--color-text-muted)] tabular-nums">
                  {idx + 1} / {items.length}
                </div>

                {/* Tab toggle */}
                <div className="flex items-center justify-center mt-[var(--space-8)]">
                  <div className="inline-flex rounded-[var(--radius-pill)] glass-card p-1 gap-1">
                    <button
                      onClick={() => setViewTab('result')}
                      className={`px-[var(--space-20)] py-[var(--space-6)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] font-medium transition-all ${
                        viewTab === 'result'
                          ? 'glass-btn-primary text-white'
                          : 'text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
                      }`}
                    >
                      Результат
                    </button>
                    <button
                      onClick={() => setViewTab('original')}
                      className={`px-[var(--space-20)] py-[var(--space-6)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] font-medium transition-all ${
                        viewTab === 'original'
                          ? 'glass-btn-primary text-white'
                          : 'text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
                      }`}
                    >
                      Исходное
                    </button>
                  </div>
                </div>

                {/* Single large photo */}
                <div className="flex justify-center">
                  <div className="w-full max-w-[380px] flex flex-col gap-[var(--space-12)]">
                    <div className="relative rounded-[var(--radius-12)] overflow-hidden aspect-[3/4] bg-[rgba(255,255,255,0.02)]">
                      {viewTab === 'result' ? (
                        item.generated_image_url && !imgErrors[`gen_${item.task_id}`] ? (
                          <img
                            src={normalizeImageUrl(item.generated_image_url)}
                            alt="Результат"
                            className="w-full h-full object-cover"
                            onError={() => setImgErrors(p => ({ ...p, [`gen_${item.task_id}`]: true }))}
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[var(--color-text-muted)] text-[14px]">
                            {imgErrors[`gen_${item.task_id}`] ? 'Фото недоступно' : 'Нет фото'}
                          </div>
                        )
                      ) : (
                        item.input_image_url && !imgErrors[`input_${item.task_id}`] ? (
                          <img
                            src={normalizeImageUrl(item.input_image_url)}
                            alt="Исходное"
                            className="w-full h-full object-cover"
                            onError={() => setImgErrors(p => ({ ...p, [`input_${item.task_id}`]: true }))}
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[var(--color-text-muted)] text-[14px]">
                            {imgErrors[`input_${item.task_id}`] ? 'Фото недоступно' : 'Нет фото'}
                          </div>
                        )
                      )}
                      <span className={`absolute top-[var(--space-8)] left-[var(--space-8)] ${viewTab === 'result' ? 'glass-badge-success' : 'glass-badge-cyan'} px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)] text-[11px] leading-[14px] font-medium text-[#E6EEF8]`}>
                        {viewTab === 'result'
                          ? (styleInfo ? `${styleInfo.icon} ${styleInfo.name}` : 'Результат')
                          : 'Исходное'}
                      </span>
                    </div>

                    {/* Score under photo */}
                    <div className="flex items-center justify-between">
                      <span className="text-[14px] leading-[20px] text-[#E6EEF8] font-medium">
                        {viewTab === 'result'
                          ? (styleInfo ? `${styleInfo.icon} ${styleInfo.name}` : (item.style || item.mode))
                          : 'Исходное фото'}
                      </span>
                      <span className="flex items-center gap-1">
                        <span className={`text-[14px] leading-[20px] tabular-nums font-semibold ${viewTab === 'result' ? 'text-[var(--color-brand-primary)]' : 'text-[var(--color-text-secondary)]'}`}>
                          {viewTab === 'result'
                            ? (item.score_after != null ? item.score_after.toFixed(2) : '—')
                            : (item.score_before != null ? item.score_before.toFixed(2) : '—')}
                        </span>
                        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                      </span>
                    </div>
                    <ProgressBar
                      value={viewTab === 'result' ? (item.score_after ?? 0) : (item.score_before ?? 0)}
                      accent={viewTab === 'result'}
                    />

                    {/* Score delta */}
                    {item.score_before != null && item.score_after != null && (
                      <div className="flex items-center justify-center gap-[var(--space-12)]">
                        <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)] tabular-nums">{item.score_before.toFixed(2)}</span>
                        <span className="text-[14px] text-[var(--color-text-muted)]">&rarr;</span>
                        <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold tabular-nums">{item.score_after.toFixed(2)}</span>
                        <span className="text-[13px] leading-[18px] text-[var(--color-success-base)]">
                          (+{(item.score_after - item.score_before).toFixed(2)})
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Perception scores */}
                {item.perception_scores && Object.keys(item.perception_scores).length > 0 && (
                  <div className="flex flex-col gap-[var(--space-12)]">
                    <span className="text-[14px] font-medium text-[#E6EEF8]">Параметры восприятия</span>
                    {Object.entries(item.perception_scores)
                      .filter(([k]) => k !== 'authenticity')
                      .map(([key, value]) => (
                        <div key={key} className="flex flex-col gap-[var(--space-4)]">
                          <div className="flex items-center justify-between">
                            <span className="text-[13px] text-[var(--color-text-secondary)]">{PARAM_LABELS[key] ?? key}</span>
                            <span className="text-[13px] tabular-nums text-[var(--color-brand-primary)]">{(value as number).toFixed(1)}</span>
                          </div>
                          <ProgressBar value={value as number} accent />
                        </div>
                      ))}
                  </div>
                )}

                {downloadError && (
                  <p className="text-[13px] text-red-400 text-center">
                    Не удалось скачать файл. Попробуйте позже.
                  </p>
                )}

                {/* Actions */}
                <div className="flex flex-col gap-[var(--space-8)]">
                  {onImprove && (
                    <button
                      onClick={() => item.generated_image_url && onImprove(normalizeImageUrl(item.generated_image_url))}
                      disabled={!item.generated_image_url}
                      className="w-full glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-semibold text-white flex items-center justify-center gap-[var(--space-8)] disabled:opacity-40"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1.333 8A6.667 6.667 0 0012 3.333M14.667 8A6.667 6.667 0 014 12.667" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><path d="M12 1.333v2h2M4 14.667v-2H2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      Улучшить ещё
                    </button>
                  )}
                  <div className="flex gap-[var(--space-12)]">
                    <button
                      onClick={handleDownload}
                      disabled={!item.generated_image_url}
                      className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-medium text-[#E6EEF8] flex items-center justify-center gap-[var(--space-8)] disabled:opacity-40"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 2v8m0 0L5 7m3 3l3-3M3 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      Скачать
                    </button>
                    <button
                      onClick={handleShowShare}
                      disabled={shareLoading}
                      className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-medium text-[#E6EEF8] flex items-center justify-center gap-[var(--space-8)] disabled:opacity-40"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 9.333l4-2.666M6 6.667l4 2.666M12 4a2 2 0 11-4 0 2 2 0 014 0zM6 8a2 2 0 11-4 0 2 2 0 014 0zM12 12a2 2 0 11-4 0 2 2 0 014 0z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      {shareLoading ? 'Загрузка...' : 'Поделиться'}
                    </button>
                  </div>
                  {shareData && <ShareButtons url={shareData.url} text={shareData.text} />}
                </div>
              </motion.div>
            </AnimatePresence>
          )}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
