import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, Link } from 'react-router-dom';
import { CoinIcon } from '@ai-ds/core/icons';
import {
  getApprovalProbabilityAfterPct,
  isApprovalProbabilityScenario,
  normalizePostPaymentPath,
} from '../../scenarios/config';
import { createPayment, handleCreatePaymentError, readGenerationWarnings } from '../../lib/api';
import { rememberFlowReturnPath, rememberFlowStep } from '../../lib/flow-resume';
import { savePhotoBeforePayment } from '../../lib/photo-persist';
import { PERCEPTION_FACTS, getRandomFact } from '../../data/ai-facts';
import { CATEGORIES } from '../../data/styles';
import {
  AB_MODELS,
  formatAbCredits,
} from '../../data/ab-models';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import ShareModal from '../ShareModal';
import StyleSettingsModal from './StyleSettingsModal';
import { PlaceholderUpgrade } from '../effects/PlaceholderArt';
import { useToast } from '../Toast';
import type { ResolvedSlots } from '../../lib/api';

interface Props {
  onGoToStep: (step: 'upload' | 'analysis' | 'style') => void;
  onOpenStorage?: () => void;
}

function parseTaskProgress(
  status: string | undefined,
  resolveLabel: (step: string) => string,
): { label: string; percent: number } | null {
  if (!status) return null;
  const match = status.match(/^(\S+)\s+(\d+)\/(\d+)$/);
  if (!match) return null;
  const [, step, current, total] = match;
  const cur = parseInt(current, 10);
  const tot = parseInt(total, 10);
  const percent = tot > 0 ? Math.round((cur / tot) * 100) : 0;
  return { label: resolveLabel(step), percent };
}

// Re-project the backend's resolved_slots payload onto the keys
// StyleSettingsModal accepts as `hints`. Fields that the modal manages
// 1:1 (lighting/weather/time_of_day/season) keep their names; scene
// and clothing are renamed to *_override because that's how the modal
// stores free-form overrides. We deliberately drop trigger (read-only
// in the modal) and expression / random_picks / substitutions
// (not part of the editable surface).
function resolvedSlotsToHints(slots: ResolvedSlots | null | undefined): Record<string, string> {
  if (!slots) return {};
  const hints: Record<string, string> = {};
  if (typeof slots.lighting === 'string' && slots.lighting.trim()) hints.lighting = slots.lighting;
  if (typeof slots.weather === 'string' && slots.weather.trim()) hints.weather = slots.weather;
  if (typeof slots.time_of_day === 'string' && slots.time_of_day.trim()) hints.time_of_day = slots.time_of_day;
  if (typeof slots.season === 'string' && slots.season.trim()) hints.season = slots.season;
  if (typeof slots.scene === 'string' && slots.scene.trim()) hints.scene_override = slots.scene;
  if (typeof slots.clothing === 'string' && slots.clothing.trim()) hints.clothing_override = slots.clothing;
  return hints;
}

export default function StepGenerate({ onGoToStep, onOpenStorage }: Props) {
  const app = useApp();
  const { t } = useTranslation('wizard');
  const navigate = useNavigate();
  const toast = useToast();

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

  // Approval-probability flow (visa + document-photo): the headline
  // becomes a fixed 98.9% once the user successfully regenerates the
  // photo. ``displayApprovalAfter`` mirrors the data-driven
  // ``analysis_display.success_probability_after_pct`` from
  // ``data/scenarios.json`` (98.9 for every visa + document-photo).
  const isApproval = isApprovalProbabilityScenario(app.scenarioSlug);
  const approvalTargetPct = getApprovalProbabilityAfterPct(app.scenarioSlug);
  const displayApprovalAfter =
    isApproval && hasGenResult ? (approvalTargetPct ?? 98.9) : null;

  const generationWarnings = readGenerationWarnings(app.currentTask?.result ?? null);

  const [streamedFact, setStreamedFact] = useState('');
  const [showNoCredits, setShowNoCredits] = useState(false);
  const [docPaywallOpen, setDocPaywallOpen] = useState(false);

  const [currentFact, setCurrentFact] = useState(() => PERCEPTION_FACTS.social[0]);
  const factIdxRef = useRef(0);
  const factTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [frozenStyle, setFrozenStyle] = useState<{ name: string; score: number } | null>(null);
  const [genFailed, setGenFailed] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);

  const isRunning = app.isGenerating && !hasGenResult;
  const progress = parseTaskProgress(app.currentTask?.status, (step) => {
    const key = `generate.stepLabels.${step}`;
    const translated = t(key);
    if (translated && translated !== key) return translated;
    return `${step}...`;
  });

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
      toast.show(handleCreatePaymentError(e), 'warning');
      setPaymentLoading(false);
    }
  }

  const [shareData, setShareData] = useState<{ url: string; text: string; imageUrl: string } | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareModalOpen, setShareModalOpen] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);

  async function handleDownload() {
    if (!app.generatedImageUrl) return;
    setDownloadError(false);
    setDownloadLoading(true);
    try {
      const base = app.generatedImageUrl;
      const sep = base.includes('?') ? '&' : '?';
      const url = `${base}${sep}download=1`;
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) {
        setDownloadError(true);
        return;
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = isDocPaywall ? 'document-photo.jpg' : 'look-studio-photo.jpg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(a.href), 2_000);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloadLoading(false);
    }
  }

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

  const cardLabel = hasGenResult
    ? selectedStyle.name
    : frozenStyle
      ? frozenStyle.name
      : app.photo ? selectedStyle.name : t('generate.fallbackCardLabel');

  const cardScore = displayAfterScore != null
    ? displayAfterScore
    : frozenStyle
      ? frozenStyle.score
      : predictedAfterScore;

  const cardScoreIsApprox = displayAfterScore == null && (!!frozenStyle || predictedAfterScore != null);

  const directionLabel = CATEGORIES.find(c => c.id === activeTab)?.label ?? '';
  const showSelectionSummary = !hasGenResult && !isDocPaywall;
  const showStartGenerateCta = !isDocPaywall && !hasGenResult && !isRunning && !genFailed && !!app.photo;

  return (
    <div className="flex flex-col gap-[var(--space-24)] tablet:gap-[var(--space-32)] w-full max-w-[800px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-4)] text-center">
        <h2 className="text-[20px] tablet:text-[24px] leading-[1.2] font-semibold text-[var(--color-text-primary)]">
          {hasGenResult ? t('generate.headings.result') : isRunning ? t('generate.headings.running') : genFailed ? t('generate.headings.failed') : t('generate.headings.ready')}
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          {hasGenResult
            ? t('generate.subtitles.result')
            : genFailed
              ? t('generate.subtitles.failed')
              : isRunning
                ? t('generate.subtitles.running')
                : t('generate.subtitles.ready')}
        </p>
      </div>

      {/* Selection summary: "Вы выбрали" label sits in the same row as pills */}
      {showSelectionSummary && selectedStyle && (
        <div className="flex flex-wrap items-center justify-center gap-x-[var(--space-8)] gap-y-[var(--space-4)] text-[13px] leading-[18px]">
          <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)]">{t('generate.selection.label')}</span>
          {directionLabel && (
            <button
              type="button"
              onClick={() => onGoToStep('analysis')}
              className="glass-btn-ghost px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[var(--color-text-primary)] inline-flex items-center gap-[var(--space-6)]"
            >
              <span className="text-[var(--color-text-muted)]">{t('generate.selection.direction')}</span>
              <span className="font-medium">«{directionLabel}»</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => onGoToStep('style')}
            className="glass-btn-ghost px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[var(--color-text-primary)] inline-flex items-center gap-[var(--space-6)]"
          >
            <span className="text-[var(--color-text-muted)]">{t('generate.selection.style')}</span>
            <span className="font-medium">«{selectedStyle.name}»</span>
          </button>
        </div>
      )}

      {/* v1.27.3 — soft-substitution notice. Shown when one or more
          unrecognised user inputs were replaced by the closest
          whitelist value during prompt assembly. */}
      {hasGenResult && generationWarnings.length > 0 && (
        <div className="max-w-[640px] mx-auto w-full px-[var(--space-16)]">
          <div className="glass-card border border-amber-300/30 bg-amber-500/10 rounded-[var(--radius-md)] px-[var(--space-12)] py-[var(--space-8)]">
            <p className="text-[12px] leading-[16px] font-medium text-amber-200 mb-[var(--space-4)]">
              {t('generate.warningsTitle')}
            </p>
            <ul className="text-[12px] leading-[16px] text-[var(--color-text-primary)] list-disc pl-[var(--space-16)] space-y-[2px]">
              {generationWarnings.map((msg, idx) => (
                <li key={idx}>{msg}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Photo column: photo card + result-action stacks below.
          Width is fixed to 260px so the action buttons under the photo
          align exactly with its width. */}
      <div className="flex flex-col items-center gap-[var(--space-16)] w-full">
        <div className="w-full max-w-[260px] flex flex-col gap-[var(--space-16)]">
          {/* Image card */}
          <div className="gradient-border-card glass-card flex flex-col w-full rounded-[var(--radius-12)] overflow-hidden">
            <div className="aspect-[4/5] bg-[var(--glass-surface-soft)] overflow-hidden relative">
              {hasGenResult && (
                <>
                  <img
                    src={app.generatedImageUrl!}
                    alt={t('generate.altGenerated')}
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
                    aria-label={t('generate.aiBadgeAria')}
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
                      {t('generate.aiBadge')}
                    </span>
                  </div>
                </>
              )}
              {imageLoadError && app.generatedImageUrl && (
                <div className="w-full h-full flex flex-col items-center justify-center gap-3 text-center p-4">
                  <p className="text-[14px] text-[var(--color-text-muted)]">{t('generate.imageLoadFailed')}</p>
                  <button
                    className="px-4 py-2 rounded-lg text-[13px] font-medium glass-card hover:opacity-80 transition-opacity"
                    onClick={() => { app.clearGeneratedImage(); setImageLoadError(false); }}
                  >
                    {t('generate.regenerate')}
                  </button>
                </div>
              )}
              {!hasGenResult && isRunning && (
                <>
                  <PlaceholderUpgrade className="w-full h-full opacity-50 gen-sim-pulse text-[var(--color-text-secondary)]" />
                  <div className="absolute inset-0 z-10 flex flex-col items-center justify-end pb-[var(--space-16)] gap-[var(--space-8)] bg-gradient-to-t from-black/70 via-transparent to-transparent">
                    <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.6)', borderTopColor: 'transparent' }} />
                    <span className="text-[12px] leading-[16px] text-[var(--color-text-primary)] font-medium text-center px-[var(--space-8)]">
                      {progress?.label ?? t('generate.stepLabels.fallback')}
                    </span>
                    <div className="w-[80%] h-1 rounded-full glass-progress-track overflow-hidden">
                      <div className="h-full rounded-full glass-progress-fill transition-all duration-500" style={{ width: `${progress?.percent ?? 10}%` }} />
                    </div>
                  </div>
                </>
              )}
              {!hasGenResult && genFailed && !isRunning && (
                <div className="w-full h-full relative">
                  <PlaceholderUpgrade
                    className="w-full h-full text-[var(--color-text-secondary)]"
                    style={{ filter: 'blur(16px) saturate(1.6) brightness(0.6)', transform: 'scale(1.1)' }}
                  />
                  <div
                    className="absolute inset-0"
                    style={{
                      background:
                        'linear-gradient(135deg, rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.25) 0%, rgba(0,0,0,0.3) 100%)',
                    }}
                  />
                  <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-[var(--space-8)] text-center px-[var(--space-12)]">
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="text-[var(--color-text-primary)]"><circle cx="16" cy="16" r="14" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.5"/><path d="M16 10v8M16 22h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
                    <span className="text-[13px] leading-[18px] text-[var(--color-text-primary)] font-medium">{t('generate.genFailedShort')}</span>
                  </div>
                </div>
              )}
              {!hasGenResult && !isRunning && !genFailed && (
                <PlaceholderUpgrade className="w-full h-full opacity-50 text-[var(--color-text-secondary)]" />
              )}
            </div>

            {/* Card footer */}
            <div className="flex flex-col gap-[var(--space-4)] px-[var(--space-10)] py-[var(--space-6)]">
              <div className="flex items-center justify-between">
                <span className="text-[13px] leading-[18px] text-[var(--color-text-primary)] font-medium">{cardLabel}</span>
                {isRunning ? null : isApproval && displayApprovalAfter != null ? (
                  <span className="flex items-baseline gap-1">
                    <span className="text-[14px] leading-[18px] font-semibold text-[var(--color-brand-primary)]">
                      {displayApprovalAfter.toFixed(1)}
                    </span>
                    <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">%</span>
                  </span>
                ) : isApproval ? null : cardScore != null && (
                  <span className="flex items-center gap-1">
                    <span className="text-[14px] leading-[18px] font-semibold text-[var(--color-brand-primary)]">
                      {cardScoreIsApprox ? '~' : ''}{cardScore.toFixed(2)}
                    </span>
                    <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                  </span>
                )}
              </div>
              {isRunning ? (
                <ProgressBar value={progress?.percent ?? 10} max={100} accent />
              ) : isApproval && displayApprovalAfter != null ? (
                <ProgressBar value={displayApprovalAfter} max={100} accent />
              ) : isApproval ? null : cardScore != null ? (
                <ProgressBar value={cardScore} accent />
              ) : null}
              {!isRunning && isApproval && displayApprovalAfter != null && (
                <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] mt-[2px]">
                  {t('generate.approvalAfter')}
                </span>
              )}
            </div>
          </div>

          {/* Streaming fact while running (below photo). Размещаем под
              карточкой, чтобы не «прыгал» layout: при запуске карточка
              остаётся на одном месте, а текст подменяется внизу. */}
          {isRunning && (
            <div className="flex items-start justify-center gap-[var(--space-8)] px-[var(--space-8)] w-full">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0 mt-[2px]">
                <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M9 21h6M10 17v1a2 2 0 0 0 4 0v-1" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <p className="text-[12px] tablet:text-[14px] leading-[16px] tablet:leading-[20px] text-[var(--color-text-primary)] text-left">
                {streamedFact}
                <span className="inline-block w-[2px] h-[12px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" />
              </p>
            </div>
          )}

          {/* Result actions: Download/Share stack directly under photo */}
          {!isRunning && hasGenResult && app.generatedImageUrl && (
            <div className="flex flex-col gap-[var(--space-8)] w-full">
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloadLoading}
                className="glass-btn-primary w-full py-[var(--space-12)] text-[14px] leading-[20px] rounded-[var(--radius-12)] font-medium inline-flex items-center justify-center gap-[var(--space-6)] disabled:opacity-50"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v8m0 0L5 7m3 3l3-3M3 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                {downloadLoading ? t('generate.downloading') : t('generate.downloadCta')}
              </button>
              <button
                onClick={handleShowShare}
                disabled={shareLoading}
                className="glass-btn-ghost w-full py-[var(--space-12)] text-[14px] leading-[20px] rounded-[var(--radius-12)] font-medium disabled:opacity-40 inline-flex items-center justify-center gap-[var(--space-6)]"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M12 5a2 2 0 1 0-1.9-1.4L5.9 6.1a2 2 0 1 0 0 3.8l4.2 2.5A2 2 0 1 0 11 11l-4.2-2.5a2 2 0 0 0 0-1L11 5c.3.3.6.4 1 .5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {shareLoading ? t('generate.shareLoading') : t('generate.shareCta')}
              </button>
              {downloadError && (
                <p className="text-[11px] leading-[14px] text-red-400 text-center">
                  {t('generate.downloadError')}
                </p>
              )}
            </div>
          )}

          {/* Result actions: secondary stack — улучшить → настройки → стиль → фото */}
          {hasGenResult && (
            <div className="flex flex-col gap-[var(--space-8)] w-full">
              <button
                onClick={handleImproveGenerated}
                className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-12)] font-medium"
              >
                {t('generate.improveMore')}
              </button>
              <button
                onClick={() => setSettingsModalOpen(true)}
                className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-12)] font-medium"
                title={t('generate.settingsTitle')}
              >
                {t('generate.settings')}
              </button>
              <button
                onClick={() => {
                  app.resetGeneration();
                  setFrozenStyle(null);
                  onGoToStep('style');
                }}
                className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-12)] font-medium"
              >
                {isDocPaywall ? t('generate.anotherFormat') : t('generate.anotherStyle')}
              </button>
              <button
                onClick={() => {
                  app.resetGeneration();
                  setFrozenStyle(null);
                  onGoToStep('upload');
                }}
                className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-12)] font-medium"
              >
                {t('generate.anotherPhoto')}
              </button>
              {app.scenarioPrimaryCtaMainApp && (
                <Link
                  to="/app"
                  className="glass-btn-ghost w-full py-[var(--space-10)] text-[13px] leading-[18px] rounded-[var(--radius-12)] font-medium no-underline inline-flex items-center justify-center"
                >
                  {t('generate.openMain')}
                </Link>
              )}
            </div>
          )}
        </div>
      </div>

      {/* v1.79 — tier «Стандарт / Премиум»: premium → FAL quality=high
          (тот же пайплайн), 5 кредитов; при сбое — полный refund. */}
      {showStartGenerateCta && !isDocPaywall && (
        <div className="shrink-0 flex flex-col items-center gap-[var(--space-6)] w-full max-w-[520px] mx-auto px-[var(--space-8)]">
          <div className="flex flex-wrap items-center justify-center gap-[var(--space-4)]">
            <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] mr-[var(--space-4)]">{t('generate.modeLabel')}</span>
            {AB_MODELS.map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => app.setTier(m.key)}
                title={m.description}
                className={`px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[12px] leading-[16px] font-medium transition-all ${
                  app.tier === m.key
                    ? 'glass-btn-primary text-white'
                    : 'glass-btn-ghost text-[var(--color-text-secondary)]'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">
            {formatAbCredits(app.tier)}
          </span>
        </div>
      )}

      {/* Primary CTA — explicit "Запустить генерацию" for non-document scenarios */}
      {showStartGenerateCta && (
        <div className="shrink-0 flex flex-col items-center gap-[var(--space-8)]">
          <button
            onClick={handleGenerate}
            disabled={app.isGenerating}
            className="glass-btn-primary px-[var(--space-32)] py-[var(--space-10)] tablet:py-[var(--space-8)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
          >
            {t('generate.startGeneration')}
          </button>
        </div>
      )}

      {/* Document scenario — primary CTA (always visible; no-credit path opens a modal). */}
      {isDocPaywall && !hasGenResult && !isRunning && !genFailed && app.isAuthenticated && !!app.photo && (
        <div className="shrink-0 flex flex-col items-center gap-[var(--space-8)]">
          <button
            onClick={handleGenerate}
            disabled={app.isGenerating}
            className="glass-btn-primary px-[var(--space-32)] py-[var(--space-10)] tablet:py-[var(--space-8)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
          >
            {t('generate.generatePhoto')}
          </button>
        </div>
      )}

      {/* Failure recovery */}
      <div className="flex flex-col items-center gap-[var(--space-6)]">
        {genFailed && !isRunning && !hasGenResult && (
          <div className="flex flex-col items-center gap-[var(--space-8)] w-full max-w-[520px] mx-auto px-[var(--space-8)]">
            {app.error && (
              <p className="text-[12px] leading-[16px] text-[var(--color-text-secondary)] text-center whitespace-pre-wrap">
                {app.error}
              </p>
            )}
            <div className="flex flex-wrap items-center justify-center gap-[var(--space-8)] w-full">
              <button
                onClick={() => { app.clearError(); setGenFailed(false); handleGenerate(); }}
                className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
              >
                {t('generate.tryAgain')}
              </button>
              <button
                onClick={() => {
                  app.clearError();
                  app.resetGeneration();
                  setGenFailed(false);
                  onGoToStep('upload');
                }}
                className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
              >
                {t('generate.anotherPhoto')}
              </button>
              {/* v1.24: show top-up CTA when the backend flagged
                  no-credits or the error text mentions кредит/баланс,
                  so the user never gets stuck with a blank message. */}
              {(app.noCreditsError
                || /кредит|баланс|no_credits|оплат|credit|balance/i.test(app.error ?? '')) && (
                <button
                  onClick={goToPricing}
                  className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] text-[var(--color-brand-primary)]"
                >
                  {t('generate.topUp')}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {docPaywallOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card rounded-[var(--radius-16)] p-[var(--space-24)] max-w-sm w-full mx-4 flex flex-col items-center gap-[var(--space-16)] text-center">
            <CoinIcon size={40} className="text-[var(--color-brand-primary)]" />
            <h3 className="text-[18px] font-semibold text-[var(--color-text-primary)]">{t('generate.docPaywallTitle')}</h3>
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              {t('generate.docPaywallDesc')}
            </p>
            <div className="flex gap-[var(--space-12)] w-full">
              <button
                className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-medium text-[var(--color-text-primary)]"
                onClick={() => setDocPaywallOpen(false)}
                disabled={paymentLoading}
              >
                {t('generate.close')}
              </button>
              <button
                className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-semibold text-white disabled:opacity-60"
                onClick={() => handleDocPaywallBuy(paymentPackQty)}
                disabled={paymentLoading}
              >
                {paymentLoading ? t('generate.loading') : t('generate.docPaywallCta', { count: paymentPackQty })}
              </button>
            </div>
          </div>
        </div>
      )}

      {(showNoCredits || app.noCreditsError) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card rounded-[var(--radius-16)] p-[var(--space-24)] max-w-sm w-full mx-4 flex flex-col items-center gap-[var(--space-16)] text-center">
            <CoinIcon size={40} className="text-[var(--color-brand-primary)]" />
            <h3 className="text-[18px] font-semibold text-[var(--color-text-primary)]">{t('generate.noCreditsTitle')}</h3>
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              {t('generate.noCreditsDesc')}
            </p>
            <div className="flex gap-[var(--space-12)] w-full">
              <button
                className="flex-1 glass-btn-ghost rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-medium text-[var(--color-text-primary)]"
                onClick={() => { setShowNoCredits(false); app.clearNoCreditsError(); }}
              >
                {t('generate.close')}
              </button>
              <button
                className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-semibold text-white"
                onClick={goToPricing}
              >
                {t('generate.topUp')}
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

      <StyleSettingsModal
        open={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        styleId={app.selectedStyleKey}
        initialHints={resolvedSlotsToHints(
          (app.currentTask?.result as { resolved_slots?: ResolvedSlots } | null)
            ?.resolved_slots,
        )}
        onApply={(hints) => {
          app.resetGeneration();
          setFrozenStyle(null);
          app.generate(undefined, undefined, hints);
        }}
      />
    </div>
  );
}
