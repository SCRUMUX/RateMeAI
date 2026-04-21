import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import type { TaskHistoryItem } from '../lib/api';
import { createShare } from '../lib/api';
import { normalizeImageUrl } from '../lib/image-url';
import { STYLES_BY_CATEGORY } from '../data/styles';
import { DOCUMENT_FORMAT_ITEMS } from '../scenarios/extraStyles';
import { useApp } from '../context/AppContext';
import ProgressBar from './wizard/ProgressBar';
import ShareButtons from './ShareButtons';

const STYLE_LOOKUP: Record<string, { name: string; icon: string }> = {};
for (const styles of Object.values(STYLES_BY_CATEGORY)) {
  for (const s of styles) {
    STYLE_LOOKUP[s.key] = { name: s.name, icon: s.icon };
  }
}
for (const s of DOCUMENT_FORMAT_ITEMS) {
  STYLE_LOOKUP[s.key] = { name: s.name, icon: s.icon };
}
const DOCUMENT_STYLE_KEYS = new Set(DOCUMENT_FORMAT_ITEMS.map(d => d.key));

interface Props {
  items: TaskHistoryItem[];
  open: boolean;
  onClose: () => void;
  onImprove?: (imageUrl: string) => void;
}

const SWIPE_THRESHOLD = 50;

export default function StorageModal({ items, open, onClose, onImprove }: Props) {
  const { activeCategory, fetchTaskHistory } = useApp();
  const navigate = useNavigate();
  const [idx, setIdx] = useState(0);
  const [dir, setDir] = useState(0);
  const [shareData, setShareData] = useState<{ url: string; text: string; imageUrl: string } | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);
  const [imgErrors, setImgErrors] = useState<Record<string, boolean>>({});

  const taskIdRef = useRef<string | null>(null);

  const item = items[idx];

  useEffect(() => {
    if (open) { setIdx(0); }
    if (!open) { setShareData(null); setShareLoading(false); }
  }, [open]);

  useEffect(() => {
    if (open) {
      void fetchTaskHistory();
    }
  }, [open, fetchTaskHistory]);

  useEffect(() => {
    if (!open || !item?.task_id) return;

    const currentTaskId = item.task_id;
    taskIdRef.current = currentTaskId;
    setShareData(null);
    setShareLoading(true);

    createShare(item.task_id)
      .then(res => {
        if (taskIdRef.current !== currentTaskId) return;
        setShareData({ url: res.deep_link, text: res.caption, imageUrl: res.image_url || '' });
      })
      .catch(() => {
        if (taskIdRef.current !== currentTaskId) return;
        const fallbackImg = item.generated_image_url ? normalizeImageUrl(item.generated_image_url) : '';
        setShareData({ url: '', text: '', imageUrl: fallbackImg });
      })
      .finally(() => setShareLoading(false));
  }, [open, item?.task_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const styleInfo = item ? STYLE_LOOKUP[item.style] : null;
  const canPrev = idx > 0;
  const canNext = idx < items.length - 1;

  const goPrev = useCallback(() => {
    if (!canPrev) return;
    setDir(-1);
    setIdx(i => i - 1);
    setShareData(null);
  }, [canPrev]);

  const goNext = useCallback(() => {
    if (!canNext) return;
    setDir(1);
    setIdx(i => i + 1);
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

  function handleDragEnd(_: unknown, info: { offset: { x: number } }) {
    if (info.offset.x < -SWIPE_THRESHOLD && canNext) goNext();
    else if (info.offset.x > SWIPE_THRESHOLD && canPrev) goPrev();
  }

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
                className="absolute top-3 right-3 w-10 h-10 flex items-center justify-center rounded-full glass-btn-ghost text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
              >
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none">
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
              className="relative gradient-border-card glass-card rounded-[var(--radius-12)] w-full max-w-[420px] max-h-[calc(100dvh-32px)] p-[var(--space-16)] flex flex-col gap-[var(--space-12)]"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Close button -- ghost without background */}
              <button
                onClick={onClose}
                aria-label="Закрыть"
                className="absolute top-3 right-3 z-10 w-10 h-10 flex items-center justify-center rounded-full bg-transparent text-[var(--color-text-muted)] hover:text-[#E6EEF8] transition-colors"
              >
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>

              {/* Header row: counter + retention notice (we intentionally do not
                  keep the original photo, so there is no "Исходное" tab) */}
              <div className="shrink-0 flex items-center justify-between gap-[var(--space-8)] pr-[var(--space-32)]">
                <span className="text-[12px] text-[var(--color-text-muted)] tabular-nums shrink-0">
                  {items.length > 1 ? `${idx + 1} / ${items.length}` : 'Ваша генерация'}
                </span>
                <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] text-right">
                  Генерация хранится 24 часа —<br />сохраните фото удобным способом.
                </span>
              </div>

              {/* Photo with swipe — fixed aspect keeps the card stable between slide transitions */}
              <div className="shrink-0 relative w-full max-w-[380px] mx-auto aspect-[4/5] rounded-[var(--radius-12)] overflow-hidden bg-[rgba(255,255,255,0.02)]">
                <AnimatePresence mode="wait" custom={dir} initial={false}>
                  <motion.div
                    key={item.task_id}
                    custom={dir}
                    initial={{ x: dir > 0 ? 80 : dir < 0 ? -80 : 0, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: dir > 0 ? -80 : 80, opacity: 0 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    drag={items.length > 1 ? 'x' : false}
                    dragConstraints={{ left: 0, right: 0 }}
                    dragElastic={0.15}
                    onDragEnd={handleDragEnd}
                    className="absolute inset-0 cursor-grab active:cursor-grabbing"
                  >
                    {item.generated_image_url && !imgErrors[`gen_${item.task_id}`] ? (
                      <img
                        src={normalizeImageUrl(item.generated_image_url)}
                        alt="Результат"
                        className="w-full h-full object-cover select-none pointer-events-none"
                        draggable={false}
                        onError={() => setImgErrors(p => ({ ...p, [`gen_${item.task_id}`]: true }))}
                      />
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-[var(--color-text-muted)] text-[13px] text-center px-6">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <rect x="3" y="11" width="18" height="10" rx="2" />
                          <path d="M7 11V7a5 5 0 0110 0v4" />
                        </svg>
                        <span>
                          {item.purged
                            ? 'Генерация удалена по политике хранения (24 часа).'
                            : imgErrors[`gen_${item.task_id}`]
                              ? 'Фото недоступно'
                              : 'Нет фото'}
                        </span>
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>

                {canPrev && (
                  <button
                    onClick={goPrev}
                    aria-label="Предыдущее фото"
                    className="flex absolute left-2 top-1/2 -translate-y-1/2 w-12 h-12 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75 transition-all shadow-[0_4px_12px_rgba(0,0,0,0.35)] z-10"
                  >
                    <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                )}
                {canNext && (
                  <button
                    onClick={goNext}
                    aria-label="Следующее фото"
                    className="flex absolute right-2 top-1/2 -translate-y-1/2 w-12 h-12 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75 transition-all shadow-[0_4px_12px_rgba(0,0,0,0.35)] z-10"
                  >
                    <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><path d="M8 4L14 10L8 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                )}
              </div>

              {/* Dots navigation */}
              {items.length > 1 && (
                <div className="shrink-0 flex items-center justify-center gap-1.5">
                  {items.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => { setDir(i > idx ? 1 : -1); setIdx(i); setShareData(null); }}
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
                <span className="text-[13px] leading-[18px] text-[#E6EEF8] font-medium truncate flex items-center gap-1.5">
                  {styleInfo ? `${styleInfo.icon} ${styleInfo.name}` : (item.style || item.mode)}
                  {DOCUMENT_STYLE_KEYS.has(item.style) && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] leading-[12px] font-medium"
                      style={{ background: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.15)', color: 'rgb(var(--accent-r),var(--accent-g),var(--accent-b))' }}
                    >
                      документ
                    </span>
                  )}
                </span>
                <span className="flex items-center gap-1.5 shrink-0">
                  <span className="text-[13px] leading-[18px] tabular-nums font-semibold text-[var(--color-brand-primary)]">
                    {item.score_after != null ? item.score_after.toFixed(2) : '—'}
                  </span>
                  {item.score_before != null && item.score_after != null && (
                    <span className="text-[11px] leading-[14px] text-[var(--color-success-base)] tabular-nums font-medium">
                      +{(item.score_after - item.score_before).toFixed(2)}
                    </span>
                  )}
                </span>
              </div>
              <div className="shrink-0 px-1">
                <ProgressBar value={item.score_after ?? 0} accent />
              </div>

              {downloadError && (
                <p className="shrink-0 text-[12px] text-red-400 text-center">
                  Не удалось скачать файл. Попробуйте позже.
                </p>
              )}

              {/* Actions: Improve + Download */}
              <div className="shrink-0 flex gap-[var(--space-8)]">
                {onImprove && (
                  <button
                    onClick={() => item.generated_image_url && onImprove(normalizeImageUrl(item.generated_image_url))}
                    disabled={!item.generated_image_url}
                    className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-8)] text-[13px] font-semibold text-white flex items-center justify-center gap-1.5 disabled:opacity-40"
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M1.333 8A6.667 6.667 0 0012 3.333M14.667 8A6.667 6.667 0 014 12.667" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><path d="M12 1.333v2h2M4 14.667v-2H2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    Улучшить
                  </button>
                )}
                <button
                  onClick={handleDownload}
                  disabled={!item.generated_image_url}
                  className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-8)] text-[13px] font-medium text-[#E6EEF8] flex items-center justify-center gap-1.5 disabled:opacity-40"
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v8m0 0L5 7m3 3l3-3M3 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Скачать
                </button>
              </div>

              {DOCUMENT_STYLE_KEYS.has(item.style) && (
                <button
                  onClick={() => { onClose(); navigate('/dokumenty'); }}
                  className="shrink-0 w-full glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-8)] text-[13px] font-medium text-[#E6EEF8] flex items-center justify-center gap-1.5"
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 2h5.172a2 2 0 0 1 1.414.586l2.828 2.828A2 2 0 0 1 14 6.828V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><path d="M9 2v4h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Фото на документы
                </button>
              )}

              {/* Share -- reserved slot so height stays stable across slides */}
              <div className="shrink-0 min-h-[44px] flex items-center justify-center">
                {shareLoading ? (
                  <div className="w-5 h-5 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                ) : shareData ? (
                  <div className="w-full">
                    <ShareButtons url={shareData.url} text={shareData.text} imageUrl={shareData.imageUrl} />
                  </div>
                ) : null}
              </div>
            </motion.div>
          )}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
