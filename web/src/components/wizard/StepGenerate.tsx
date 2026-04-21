import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { CoinIcon } from '@ai-ds/core/icons';
import { normalizePostPaymentPath } from '../../scenarios/config';
import { createPayment, handleCreatePaymentError } from '../../lib/api';
import { rememberFlowReturnPath, rememberFlowStep } from '../../lib/flow-resume';
import { savePhotoBeforePayment } from '../../lib/photo-persist';
import { PERCEPTION_FACTS, getRandomFact } from '../../data/ai-facts';
import { CATEGORIES } from '../../data/styles';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import ShareModal from '../ShareModal';

interface Props {
  onGoToStep: (step: 'upload' | 'analysis' | 'style') => void;
  onOpenStorage?: () => void;
}

const STEP_LABELS: Record<string, string> = {
  upload: 'Загрузка фото...',
  validate: 'Проверка изображения...',
  analyze: 'AI анализ...',
  generate: 'Генерация образа...',
  finalize: 'Финализация...',
  complete: 'Готово',
};

function parseTaskProgress(status: string | undefined): { label: string; percent: number } | null {
  if (!status) return null;
  const match = status.match(/^(\S+)\s+(\d+)\/(\d+)$/);
  if (!match) return null;
  const [, step, current, total] = match;
  const cur = parseInt(current, 10);
  const tot = parseInt(total, 10);
  const percent = tot > 0 ? Math.round((cur / tot) * 100) : 0;
  const label = STEP_LABELS[step] ?? `${step}...`;
  return { label, percent };
}

export default function StepGenerate({ onGoToStep, onOpenStorage }: Props) {
  const app = useApp();
  const navigate = useNavigate();

  const activeTab = app.activeCategory;
  const styles = app.effectiveStyleList;
  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : null;
  const predictedDelta = (selectedStyle.deltaRange[0] + selectedStyle.deltaRange[1]) / 2;
  const predictedAfterScore = beforeScore != null ? +(beforeScore + predictedDelta).toFixed(2) : null;

  const [imageLoadError, setImageLoadError] = useState(false);
  const hasGenResult = !!app.generatedImageUrl && !imageLoadError;
  const genAfterScore = app.afterScore;

  const displayAfterScore =
    (genAfterScore != null && beforeScore != null && genAfterScore >= beforeScore)
      ? genAfterScore
      : (genAfterScore != null && beforeScore == null)
        ? genAfterScore
        : predictedAfterScore;

  const [viewTab, setViewTab] = useState<'result' | 'original'>('result');
  const [streamedFact, setStreamedFact] = useState('');
  const [showNoCredits, setShowNoCredits] = useState(false);
  const [docPaywallOpen, setDocPaywallOpen] = useState(false);

  const [currentFact, setCurrentFact] = useState(() => PERCEPTION_FACTS.social[0]);
  const factIdxRef = useRef(0);
  const factTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [frozenStyle, setFrozenStyle] = useState<{ name: string; score: number } | null>(null);
  const [genFailed, setGenFailed] = useState(false);

  const isRunning = app.isGenerating && !hasGenResult;
  const progress = parseTaskProgress(app.currentTask?.status);

  useEffect(() => { setViewTab('result'); }, [hasGenResult]);

  useEffect(() => {
    if (!isRunning) {
      if (factTimerRef.current) { clearInterval(factTimerRef.current); factTimerRef.current = null; }
      return;
    }
    factIdxRef.current = 0;
    const categoryFacts = PERCEPTION_FACTS[activeTab];
    setCurrentFact(categoryFacts[0]);
    factTimerRef.current = setInterval(() => {
      const { fact, index } = getRandomFact(factIdxRef.current, activeTab);
      factIdxRef.current = index;
      setCurrentFact(fact);
    }, 8000);
    return () => { if (factTimerRef.current) clearInterval(factTimerRef.current); };
  }, [isRunning, activeTab]);

  useEffect(() => {
    if (!currentFact?.text || !isRunning) {
      setStreamedFact('');
      return;
    }
    setStreamedFact('');
    let idx = 0;
    const target = currentFact.text;
    const iv = setInterval(() => {
      idx++;
      setStreamedFact(target.slice(0, idx));
      if (idx >= target.length) clearInterval(iv);
    }, 35);
    return () => clearInterval(iv);
  }, [currentFact, isRunning]);

  useEffect(() => { setImageLoadError(false); }, [app.generatedImageUrl]);

  useEffect(() => {
    if (app.error && !app.isGenerating && !hasGenResult) {
      setGenFailed(true);
    }
  }, [app.error, app.isGenerating, hasGenResult]);

  useEffect(() => {
    if (hasGenResult) {
      setGenFailed(false);
    }
  }, [hasGenResult]);

  useEffect(() => {
    if (!app.photo) {
      setFrozenStyle(null);
      setGenFailed(false);
    }
  }, [app.photo]);

  async function handleGenerate() {
    if (!app.photo) return;
    const effectiveStyle = app.selectedStyleKey || styles[0]?.key || '';
    if (!app.selectedStyleKey && effectiveStyle) {
      app.setSelectedStyleKey(effectiveStyle);
    }

    const isFirstGeneration = app.taskHistoryCount === 0 && !app.generatedImageUrl;
    if (app.balance <= 0 && !isFirstGeneration) {
      if (app.scenarioDocumentPaywall) {
        setDocPaywallOpen(true);
      } else {
        setShowNoCredits(true);
      }
      return;
    }

    setGenFailed(false);
    setFrozenStyle({ name: selectedStyle.name, score: predictedAfterScore ?? 7.0 });
    await app.generate(undefined, effectiveStyle);
  }

  async function handleImproveGenerated() {
    if (!app.generatedImageUrl) return;
    try {
      const res = await fetch(app.generatedImageUrl, { credentials: 'omit' });
      const blob = await res.blob();
      const file = new File([blob], 'improve.jpg', { type: blob.type || 'image/jpeg' });
      app.resetGeneration();
      setFrozenStyle(null);
      app.uploadPhoto(file);
      onGoToStep('upload');
    } catch { /* ignore */ }
  }

  const isDocPaywall = app.scenarioDocumentPaywall;
  const paymentPackQty = app.scenarioPaymentPackQty ?? 5;

  const [paymentLoading, setPaymentLoading] = useState(false);

  async function handleDocPaywallBuy(qty: number) {
    setPaymentLoading(true);
    try {
      const next = normalizePostPaymentPath(window.location.pathname) ?? '/app';
      rememberFlowReturnPath(next);
      rememberFlowStep('generate');
      if (app.photo) {
        await savePhotoBeforePayment(app.photo.file, {
          mode: app.activeCategory,
          style: app.selectedStyleKey,
          scenarioSlug: app.scenarioSlug ?? undefined,
        });
      }
      const res = await createPayment(qty);
      window.location.href = res.confirmation_url;
    } catch (e) {
      alert(handleCreatePaymentError(e));
      setPaymentLoading(false);
    }
  }

  const [shareData, setShareData] = useState<{ url: string; text: string; imageUrl: string } | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareModalOpen, setShareModalOpen] = useState(false);

  async function handleShowShare() {
    if (shareData) {
      setShareModalOpen(true);
      return;
    }
    setShareLoading(true);
    try {
      const res = await app.share();
      if (res) {
        setShareData({ url: res.deep_link, text: res.caption, imageUrl: res.image_url || '' });
        setShareModalOpen(true);
      }
    } catch { /* ignore */ }
    setShareLoading(false);
  }

  function goToPricing() {
    setShowNoCredits(false);
    const next = normalizePostPaymentPath(window.location.pathname) ?? '/app';
    rememberFlowReturnPath(next);
    rememberFlowStep('generate');
    navigate('/');
    setTimeout(() => document.getElementById('тарифы')?.scrollIntoView({ behavior: 'smooth' }), 300);
  }

  const showingOriginal = viewTab === 'original' && hasGenResult;

  const cardLabel = showingOriginal
    ? 'Исходное'
    : hasGenResult
      ? selectedStyle.name
      : frozenStyle
        ? frozenStyle.name
        : app.photo ? selectedStyle.name : 'Апгрейд';

  const cardScore = showingOriginal
    ? beforeScore
    : displayAfterScore != null
      ? displayAfterScore
      : frozenStyle
        ? frozenStyle.score
        : predictedAfterScore;

  const cardScoreIsApprox = showingOriginal
    ? false
    : displayAfterScore == null && (!!frozenStyle || predictedAfterScore != null);

  const directionLabel = CATEGORIES.find(c => c.id === activeTab)?.label ?? '';
  const showSelectionSummary = !hasGenResult && !isDocPaywall;
  const showStartGenerateCta = !isDocPaywall && !hasGenResult && !isRunning && !genFailed && !!app.photo;

  return (
    <div className="h-full flex flex-col tablet:flex-row gap-[var(--space-12)] tablet:gap-[var(--space-20)] w-full max-w-[800px] tablet:max-w-[960px] mx-auto min-h-0 overflow-y-auto tablet:overflow-visible tablet:items-stretch">
      {/* Left column — image card only */}
      <div className="shrink-0 flex justify-center tablet:w-[300px]">
        <div className="gradient-border-card glass-card flex flex-col w-full max-w-[300px] tablet:max-w-none rounded-[var(--radius-12)] overflow-hidden">
          <div className="aspect-[3/4] bg-[rgba(255,255,255,0.02)] overflow-hidden relative">
            {/* Original photo (when toggled) */}
            {showingOriginal && app.photo && (
              <img src={app.photo.preview} alt="Original" className="w-full h-full object-cover" />
            )}
            {showingOriginal && !app.photo && (
              <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
            )}

            {/* Generated result */}
            {!showingOriginal && hasGenResult && (
              <>
                <img
                  src={app.generatedImageUrl!}
                  alt="Generated"
                  className="w-full h-full object-cover cursor-pointer"
                  onClick={() => onOpenStorage?.()}
                  onError={() => setImageLoadError(true)}
                />
                {/* AI transparency badge — EU AI Act Art. 50 / visible disclosure.
                    Intentionally top-left, readable without zoom, and not removable
                    by the user in the preview. A matching EXIF UserComment field
                    is injected server-side (P1.5). */}
                <div
                  className="absolute top-[var(--space-8)] left-[var(--space-8)] z-20 pointer-events-none select-none"
                  aria-label="Изображение сгенерировано искусственным интеллектом"
                >
                  <span
                    className="inline-flex items-center gap-[4px] px-[8px] py-[3px] rounded-[var(--radius-pill)] text-[10px] leading-[12px] font-semibold tracking-[0.02em] text-white"
                    style={{
                      background: 'rgba(0,0,0,0.55)',
                      backdropFilter: 'blur(6px)',
                      WebkitBackdropFilter: 'blur(6px)',
                      border: '1px solid rgba(255,255,255,0.18)',
                    }}
                  >
                    <svg width="10" height="10" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path d="M8 2L9.5 6.5L14 8L9.5 9.5L8 14L6.5 9.5L2 8L6.5 6.5L8 2Z" fill="currentColor" />
                    </svg>
                    AI-generated
                  </span>
                </div>
              </>
            )}
            {!showingOriginal && imageLoadError && app.generatedImageUrl && (
              <div className="w-full h-full flex flex-col items-center justify-center gap-3 text-center p-4">
                <p className="text-[14px] text-[var(--color-text-muted)]">Не удалось загрузить изображение</p>
                <button
                  className="px-4 py-2 rounded-lg text-[13px] font-medium glass-card hover:opacity-80 transition-opacity"
                  onClick={() => { app.clearGeneratedImage(); setImageLoadError(false); }}
                >
                  Повторить генерацию
                </button>
              </div>
            )}
            {/* Generation in progress */}
            {!showingOriginal && !hasGenResult && isRunning && (
              <>
                <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50 gen-sim-pulse" />
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-end pb-[var(--space-16)] gap-[var(--space-8)]" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 60%)' }}>
                  <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.6)', borderTopColor: 'transparent' }} />
                  <span className="text-[12px] leading-[16px] text-[#E6EEF8] font-medium text-center px-[var(--space-8)]">
                    {progress?.label ?? 'Обработка...'}
                  </span>
                  <div className="w-[80%] h-1 rounded-full glass-progress-track overflow-hidden">
                    <div className="h-full rounded-full glass-progress-fill transition-all duration-500" style={{ width: `${progress?.percent ?? 10}%` }} />
                  </div>
                </div>
              </>
            )}
            {/* Generation failed */}
            {!showingOriginal && !hasGenResult && genFailed && !isRunning && (
              <div className="w-full h-full relative">
                <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover" style={{ filter: 'blur(16px) saturate(1.6) brightness(0.6)', transform: 'scale(1.1)' }} />
                <div className="absolute inset-0" style={{ background: 'linear-gradient(135deg, rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.25) 0%, rgba(0,0,0,0.3) 100%)' }} />
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-[var(--space-8)] text-center px-[var(--space-12)]">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="14" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5"/><path d="M16 10v8M16 22h.01" stroke="#E6EEF8" strokeWidth="2" strokeLinecap="round"/></svg>
                  <span className="text-[13px] leading-[18px] text-[#E6EEF8] font-medium">Не удалось сгенерировать</span>
                </div>
              </div>
            )}
            {/* Default placeholder */}
            {!showingOriginal && !hasGenResult && !isRunning && !genFailed && (
              <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50" />
            )}
          </div>

          {/* Card footer */}
          <div className="shrink-0 flex flex-col gap-[var(--space-4)] px-[var(--space-10)] py-[var(--space-6)]">
            <div className="flex items-center justify-between">
              <span className="text-[13px] leading-[18px] text-[#E6EEF8] font-medium">{cardLabel}</span>
              {isRunning && !showingOriginal ? null : cardScore != null && (
                <span className="flex items-center gap-1">
                  <span className={`text-[14px] leading-[18px] font-semibold ${showingOriginal ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-brand-primary)]'}`}>
                    {cardScoreIsApprox ? '~' : ''}{cardScore.toFixed(2)}
                  </span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              )}
            </div>
            {isRunning && !showingOriginal ? (
              <ProgressBar value={progress?.percent ?? 10} max={100} accent />
            ) : cardScore != null ? (
              <ProgressBar value={cardScore} accent={!showingOriginal} />
            ) : null}
          </div>
        </div>
      </div>

      {/* Right column — header, summary, controls, CTAs */}
      <div className="flex-1 flex flex-col gap-[var(--space-8)] tablet:gap-[var(--space-10)] tablet:min-h-0">
        {/* Header */}
        <div className="shrink-0 flex flex-col items-center tablet:items-start gap-[2px] text-center tablet:text-left">
          <h2 className="text-[18px] tablet:text-[22px] leading-[1.2] font-semibold text-[#E6EEF8]">
            {hasGenResult ? 'Результат готов' : isRunning ? 'Генерация...' : genFailed ? 'Ошибка генерации' : 'Генерация'}
          </h2>
          <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
            {hasGenResult
              ? 'Сравните с исходным и сохраните лучший вариант.'
              : genFailed
                ? 'Попробуйте запустить ещё раз — фото и настройки сохранены.'
                : isRunning
                  ? 'Обычно занимает 2–3 минуты. Можно свернуть вкладку — результат дождётся.'
                  : 'Генерация занимает 2–3 минуты. Запустите, когда будете готовы.'}
          </p>
        </div>

        {/* Selection summary: direction + style (clickable → jump to corresponding step) */}
        {showSelectionSummary && selectedStyle && (
          <div className="shrink-0 flex flex-col items-center tablet:items-start gap-[var(--space-4)]">
            <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)]">Вы выбрали</span>
            <div className="flex flex-wrap items-center justify-center tablet:justify-start gap-x-[var(--space-8)] gap-y-[var(--space-4)] text-[13px] leading-[18px]">
              {directionLabel && (
                <button
                  type="button"
                  onClick={() => onGoToStep('analysis')}
                  className="glass-btn-ghost px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[#E6EEF8] inline-flex items-center gap-[var(--space-6)]"
                >
                  <span className="text-[var(--color-text-muted)]">Направление:</span>
                  <span className="font-medium">«{directionLabel}»</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => onGoToStep('style')}
                className="glass-btn-ghost px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[#E6EEF8] inline-flex items-center gap-[var(--space-6)]"
              >
                <span className="text-[var(--color-text-muted)]">Стиль:</span>
                <span className="font-medium">«{selectedStyle.name}»</span>
              </button>
            </div>
          </div>
        )}

        {/* Tab toggle (visible only when result is ready) */}
        {hasGenResult && (
          <div className="shrink-0 flex items-center justify-center tablet:justify-start">
            <div className="inline-flex rounded-[var(--radius-pill)] glass-card p-1 gap-1">
              <button
                onClick={() => setViewTab('result')}
                className={`px-[var(--space-16)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium transition-all ${
                  viewTab === 'result'
                    ? 'glass-btn-primary text-white'
                    : 'text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
                }`}
              >
                Результат
              </button>
              <button
                onClick={() => setViewTab('original')}
                className={`px-[var(--space-16)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium transition-all ${
                  viewTab === 'original'
                    ? 'glass-btn-primary text-white'
                    : 'text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
                }`}
              >
                Исходное
              </button>
            </div>
          </div>
        )}

        {/* Slot: streaming fact while running, download CTAs when result is ready */}
        <div className="shrink-0 flex items-center justify-center tablet:justify-start min-h-[44px]">
          {isRunning && (
            <div className="flex items-start gap-[var(--space-8)]">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0 mt-[2px]">
                <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M9 21h6M10 17v1a2 2 0 0 0 4 0v-1" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[#E6EEF8] text-left">
                {streamedFact}
                <span className="inline-block w-[2px] h-[12px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" />
              </p>
            </div>
          )}
          {!isRunning && hasGenResult && app.generatedImageUrl && (
            <div className="flex flex-wrap items-center justify-center tablet:justify-start gap-[var(--space-6)]">
              <a
                href={app.generatedImageUrl}
                download={isDocPaywall ? 'document-photo.jpg' : 'ai-look-photo.jpg'}
                target="_blank"
                rel="noopener noreferrer"
                className="glass-btn-primary px-[var(--space-20)] py-[var(--space-6)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium no-underline inline-flex items-center gap-[var(--space-6)]"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v8m0 0L5 7m3 3l3-3M3 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Скачать фото
              </a>
              {app.scenarioPrimaryCtaMainApp && (
                <Link
                  to="/app"
                  className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-6)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium no-underline inline-flex items-center justify-center"
                >
                  Открыть AI Look Studio
                </Link>
              )}
            </div>
          )}
        </div>

        {/* Primary CTA — explicit "Запустить генерацию" for non-document scenarios */}
        {showStartGenerateCta && (
          <div className="shrink-0 flex flex-col items-center tablet:items-start gap-[var(--space-8)]">
            <button
              onClick={handleGenerate}
              disabled={app.isGenerating}
              className="glass-btn-primary w-full tablet:w-auto px-[var(--space-32)] py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
            >
              Запустить генерацию
            </button>
          </div>
        )}

        {/* Document scenario — primary CTA (always visible; no-credit path opens a modal). */}
        {isDocPaywall && !hasGenResult && !isRunning && !genFailed && app.isAuthenticated && !!app.photo && (
          <div className="shrink-0 flex flex-col items-center tablet:items-start gap-[var(--space-8)]">
            <button
              onClick={handleGenerate}
              disabled={app.isGenerating}
              className="glass-btn-primary w-full tablet:w-auto px-[var(--space-32)] py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
            >
              Генерировать фото
            </button>
          </div>
        )}

        {/* Secondary CTA row — pinned to bottom of right column on desktop */}
        <div className="shrink-0 flex flex-col items-center tablet:items-start gap-[var(--space-6)] tablet:mt-auto">
          {hasGenResult && (
            <div className="flex flex-wrap gap-[var(--space-6)] justify-center tablet:justify-start">
              <button
                onClick={() => {
                  app.resetGeneration();
                  setFrozenStyle(null);
                  onGoToStep('upload');
                }}
                className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-6)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium"
              >
                Другое фото
              </button>
              <button
                onClick={() => {
                  app.resetGeneration();
                  setFrozenStyle(null);
                  onGoToStep('style');
                }}
                className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-6)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium"
              >
                {isDocPaywall ? 'Другой формат' : 'Другой стиль'}
              </button>
              <button
                onClick={handleImproveGenerated}
                className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-6)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium"
              >
                Улучшить ещё
              </button>
              <button
                onClick={handleShowShare}
                disabled={shareLoading}
                className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-6)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] font-medium disabled:opacity-40"
              >
                {shareLoading ? 'Загрузка...' : 'Поделиться'}
              </button>
            </div>
          )}
          {genFailed && !isRunning && !hasGenResult && (
            <button
              onClick={() => { app.clearError(); setGenFailed(false); handleGenerate(); }}
              className="glass-btn-primary px-[var(--space-24)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
            >
              Повторить генерацию
            </button>
          )}
        </div>
      </div>

      {docPaywallOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card rounded-[var(--radius-16)] p-[var(--space-24)] max-w-sm w-full mx-4 flex flex-col items-center gap-[var(--space-16)] text-center">
            <CoinIcon size={40} className="text-[var(--color-brand-primary)]" />
            <h3 className="text-[18px] font-semibold text-[#E6EEF8]">Пополните баланс</h3>
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              Чтобы сгенерировать фото на документы, купите пакет — фото и настройки сохранятся.
            </p>
            <div className="flex gap-[var(--space-12)] w-full">
              <button
                className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-medium text-[#E6EEF8]"
                onClick={() => setDocPaywallOpen(false)}
                disabled={paymentLoading}
              >
                Закрыть
              </button>
              <button
                className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-semibold text-white disabled:opacity-60"
                onClick={() => handleDocPaywallBuy(paymentPackQty)}
                disabled={paymentLoading}
              >
                {paymentLoading ? 'Загрузка...' : `${paymentPackQty} фото — 199 ₽`}
              </button>
            </div>
          </div>
        </div>
      )}

      {(showNoCredits || app.noCreditsError) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card rounded-[var(--radius-16)] p-[var(--space-24)] max-w-sm w-full mx-4 flex flex-col items-center gap-[var(--space-16)] text-center">
            <CoinIcon size={40} className="text-[var(--color-brand-primary)]" />
            <h3 className="text-[18px] font-semibold text-[#E6EEF8]">Кредиты закончились</h3>
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              Для генерации изображений необходимо пополнить баланс.
            </p>
            <div className="flex gap-[var(--space-12)] w-full">
              <button
                className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-medium text-[#E6EEF8]"
                onClick={() => { setShowNoCredits(false); app.clearNoCreditsError(); }}
              >
                Закрыть
              </button>
              <button
                className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-semibold text-white"
                onClick={goToPricing}
              >
                Пополнить баланс
              </button>
            </div>
          </div>
        </div>
      )}

      {shareData && (
        <ShareModal
          open={shareModalOpen}
          onClose={() => setShareModalOpen(false)}
          url={shareData.url}
          text={shareData.text}
          imageUrl={shareData.imageUrl}
        />
      )}
    </div>
  );
}
