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

const PARAM_LABELS: Record<string, string> = {
  warmth: 'Тепл.',
  presence: 'Увер.',
  appeal: 'Привл.',
  trust: 'Довер.',
  competence: 'Комп.',
  hireability: 'Найм',
  social_score: 'Social',
  dating_score: 'Dating',
};

const SWIPE_THRESHOLD = 50;

export default function StorageModal({ items, open, onClose, onImprove }: Props) {
  const { activeCategory } = useApp();
  const [idx, setIdx] = useState(0);
  const [dir, setDir] = useState(0);
  const [viewTab, setViewTab] = useState<'result' | 'original'>('result');
  const [shareData, setShareData] = useState<{ url: string; text: string; imageUrl: string } | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [downloadError, setDownloadError] = useState(false);
  const [imgErrors, setImgErrors] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (open) { setIdx(0); setViewTab('result'); setShareOpen(false); setShareData(null); }
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
    setShareOpen(false);
  }, [canPrev]);

  const goNext = useCallback(() => {
    if (!canNext) return;
    setDir(1);
    setIdx(i => i + 1);
    setViewTab('result');
    setShareData(null);
    setShareOpen(false);
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
      if (!res.ok) { setDownloadError(true); return; }
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

  async function handleToggleShare() {
    if (shareOpen) { setShareOpen(false); return; }
    if (shareData) { setShareOpen(true); return; }
    if (!item?.task_id || shareLoading) return;
    setShareLoading(true);
    try {
      const res = await createShare(item.task_id);
      setShareData({ url: res.deep_link, text: res.caption, imageUrl: res.image_url || '' });
      setShareOpen(true);
    } catch { /* ignore */ }
    setShareLoading(false);
  }

  function handleDragEnd(_: unknown, info: { offset: { x: number } }) {
    if (info.offset.x < -SWIPE_THRESHOLD && canNext) goNext();
    else if (info.offset.x > SWIPE_THRESHOLD && canPrev) goPrev();
  }

  const perceptionEntries = item?.perception_scores
    ? Object.entries(item.perception_scores).filter(([k]) => k !== 'authenticity')
    : [];

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          data-category={activeCategory}
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

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
            <motion.div
              className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[420px] max-h-[calc(100dvh-32px)] p-[var(--space-12)] flex flex-col gap-[var(--space-8)]"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header row: close + counter + tabs */}
              <div className="shrink-0 flex items-center justify-between gap-2">
                <button
                  onClick={onClose}
                  className="w-8 h-8 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors shrink-0"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>

                {items.length > 1 && (
                  <span className="text-[12px] text-[var(--color-text-muted)] tabular-nums shrink-0">
                    {idx + 1} / {items.length}
                  </span>
                )}

                <div className="inline-flex rounded-[var(--radius-pill)] glass-card p-0.5 gap-0.5">
                  <button
                    onClick={() => setViewTab('result')}
                    className={`px-3 py-[3px] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                      viewTab === 'result'
                        ? 'glass-btn-primary text-white'
                        : 'text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
                    }`}
                  >
                    Результат
                  </button>
                  <button
                    onClick={() => setViewTab('original')}
                    className={`px-3 py-[3px] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                      viewTab === 'original'
                        ? 'glass-btn-primary text-white'
                        : 'text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
                    }`}
                  >
                    Исходное
                  </button>
                </div>
              </div>

              {/* Photo with swipe */}
              <div className="flex-1 min-h-0 relative">
                <AnimatePresence mode="wait" custom={dir}>
                  <motion.div
                    key={`${item.task_id}_${viewTab}`}
                    custom={dir}
                    initial={{ x: dir > 0 ? 80 : dir < 0 ? -80 : 0, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: dir > 0 ? -80 : 80, opacity: 0 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    drag={items.length > 1 ? 'x' : false}
                    dragConstraints={{ left: 0, right: 0 }}
                    dragElastic={0.15}
                    onDragEnd={handleDragEnd}
                    className="w-full h-full flex justify-center cursor-grab active:cursor-grabbing"
                  >
                    <div className="relative rounded-[var(--radius-12)] overflow-hidden bg-[rgba(255,255,255,0.02)] w-full max-w-[380px]">
                      {viewTab === 'result' ? (
                        item.generated_image_url && !imgErrors[`gen_${item.task_id}`] ? (
                          <img
                            src={normalizeImageUrl(item.generated_image_url)}
                            alt="Результат"
                            className="w-full h-full object-cover select-none pointer-events-none"
                            draggable={false}
                            onError={() => setImgErrors(p => ({ ...p, [`gen_${item.task_id}`]: true }))}
                          />
                        ) : (
                          <div className="w-full h-full min-h-[200px] flex items-center justify-center text-[var(--color-text-muted)] text-[14px]">
                            {imgErrors[`gen_${item.task_id}`] ? 'Фото недоступно' : 'Нет фото'}
                          </div>
                        )
                      ) : (
                        item.input_image_url && !imgErrors[`input_${item.task_id}`] ? (
                          <img
                            src={normalizeImageUrl(item.input_image_url)}
                            alt="Исходное"
                            className="w-full h-full object-cover select-none pointer-events-none"
                            draggable={false}
                            onError={() => setImgErrors(p => ({ ...p, [`input_${item.task_id}`]: true }))}
                          />
                        ) : (
                          <div className="w-full h-full min-h-[200px] flex items-center justify-center text-[var(--color-text-muted)] text-[14px]">
                            {imgErrors[`input_${item.task_id}`] ? 'Фото недоступно' : 'Нет фото'}
                          </div>
                        )
                      )}
                    </div>
                  </motion.div>
                </AnimatePresence>

                {/* Navigation arrows (desktop hover) */}
                {canPrev && (
                  <button
                    onClick={goPrev}
                    className="hidden tablet:flex absolute left-1 top-1/2 -translate-y-1/2 w-8 h-8 items-center justify-center rounded-full bg-black/40 text-white/70 hover:text-white hover:bg-black/60 transition-all opacity-0 group-hover:opacity-100"
                    style={{ opacity: 1 }}
                  >
                    <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                )}
                {canNext && (
                  <button
                    onClick={goNext}
                    className="hidden tablet:flex absolute right-1 top-1/2 -translate-y-1/2 w-8 h-8 items-center justify-center rounded-full bg-black/40 text-white/70 hover:text-white hover:bg-black/60 transition-all opacity-0 group-hover:opacity-100"
                    style={{ opacity: 1 }}
                  >
                    <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M8 4L14 10L8 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                )}
              </div>

              {/* Dots navigation */}
              {items.length > 1 && (
                <div className="shrink-0 flex items-center justify-center gap-1.5">
                  {items.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => { setDir(i > idx ? 1 : -1); setIdx(i); setViewTab('result'); setShareData(null); setShareOpen(false); }}
                      className={`rounded-full transition-all ${
                        i === idx
                          ? 'w-5 h-1.5 bg-[rgb(var(--accent-r),var(--accent-g),var(--accent-b))]'
                          : 'w-1.5 h-1.5 bg-[rgba(255,255,255,0.25)] hover:bg-[rgba(255,255,255,0.4)]'
                      }`}
                    />
                  ))}
                </div>
              )}

              {/* Score row */}
              <div className="shrink-0 flex items-center justify-between px-1">
                <span className="text-[13px] leading-[18px] text-[#E6EEF8] font-medium truncate">
                  {viewTab === 'result'
                    ? (styleInfo ? `${styleInfo.icon} ${styleInfo.name}` : (item.style || item.mode))
                    : 'Исходное фото'}
                </span>
                <span className="flex items-center gap-1.5 shrink-0">
                  <span className={`text-[13px] leading-[18px] tabular-nums font-semibold ${viewTab === 'result' ? 'text-[var(--color-brand-primary)]' : 'text-[var(--color-text-secondary)]'}`}>
                    {viewTab === 'result'
                      ? (item.score_after != null ? item.score_after.toFixed(2) : '—')
                      : (item.score_before != null ? item.score_before.toFixed(2) : '—')}
                  </span>
                  {viewTab === 'result' && item.score_before != null && item.score_after != null && (
                    <span className="text-[11px] leading-[14px] text-[var(--color-success-base)] tabular-nums font-medium">
                      +{(item.score_after - item.score_before).toFixed(2)}
                    </span>
                  )}
                </span>
              </div>
              <div className="shrink-0 px-1">
                <ProgressBar
                  value={viewTab === 'result' ? (item.score_after ?? 0) : (item.score_before ?? 0)}
                  accent={viewTab === 'result'}
                />
              </div>

              {/* Perception scores -- compact pills */}
              {perceptionEntries.length > 0 && (
                <div className="shrink-0 flex flex-wrap items-center justify-center gap-1.5 px-1">
                  {perceptionEntries.map(([key, value]) => (
                    <span
                      key={key}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] leading-[14px]"
                      style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)' }}
                    >
                      <span className="text-[var(--color-text-secondary)]">{PARAM_LABELS[key] ?? key}</span>
                      <span className="tabular-nums font-medium text-[var(--color-brand-primary)]">{(value as number).toFixed(1)}</span>
                    </span>
                  ))}
                </div>
              )}

              {downloadError && (
                <p className="shrink-0 text-[12px] text-red-400 text-center">
                  Не удалось скачать файл. Попробуйте позже.
                </p>
              )}

              {/* Actions + inline share */}
              <div className="shrink-0 flex flex-col gap-[var(--space-6)]">
                <div className="flex gap-[var(--space-6)]">
                  {onImprove && (
                    <button
                      onClick={() => item.generated_image_url && onImprove(normalizeImageUrl(item.generated_image_url))}
                      disabled={!item.generated_image_url}
                      className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-6)] text-[12px] font-semibold text-white flex items-center justify-center gap-1 disabled:opacity-40"
                    >
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M1.333 8A6.667 6.667 0 0012 3.333M14.667 8A6.667 6.667 0 014 12.667" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><path d="M12 1.333v2h2M4 14.667v-2H2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      Улучшить
                    </button>
                  )}
                  <button
                    onClick={handleDownload}
                    disabled={!item.generated_image_url}
                    className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-6)] text-[12px] font-medium text-[#E6EEF8] flex items-center justify-center gap-1 disabled:opacity-40"
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v8m0 0L5 7m3 3l3-3M3 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    Скачать
                  </button>
                  <button
                    onClick={handleToggleShare}
                    disabled={shareLoading}
                    className={`flex-1 rounded-[var(--radius-12)] py-[var(--space-6)] text-[12px] font-medium flex items-center justify-center gap-1 disabled:opacity-40 transition-all ${
                      shareOpen ? 'glass-btn-primary text-white' : 'glass-btn-ghost text-[#E6EEF8]'
                    }`}
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M6 9.333l4-2.666M6 6.667l4 2.666M12 4a2 2 0 11-4 0 2 2 0 014 0zM6 8a2 2 0 11-4 0 2 2 0 014 0zM12 12a2 2 0 11-4 0 2 2 0 014 0z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    {shareLoading ? '...' : 'Поделиться'}
                  </button>
                </div>

                {/* Inline share buttons */}
                <AnimatePresence>
                  {shareOpen && shareData && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2, ease: 'easeOut' }}
                      className="overflow-hidden"
                    >
                      <ShareButtons url={shareData.url} text={shareData.text} imageUrl={shareData.imageUrl} compact />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
