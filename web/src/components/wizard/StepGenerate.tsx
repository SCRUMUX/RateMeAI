import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { STYLES_BY_CATEGORY } from '../../data/styles';
import { PERCEPTION_FACTS, getRandomFact } from '../../data/ai-facts';
import StorageModal from '../StorageModal';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';

interface Props {
  onGoToStep: (step: 'upload' | 'style') => void;
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

export default function StepGenerate({ onGoToStep }: Props) {
  const app = useApp();
  const navigate = useNavigate();

  const activeTab = app.activeCategory;
  const styles = STYLES_BY_CATEGORY[activeTab];
  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : null;
  const predictedDelta = (selectedStyle.deltaRange[0] + selectedStyle.deltaRange[1]) / 2;
  const predictedAfterScore = beforeScore != null ? +(beforeScore + predictedDelta).toFixed(2) : null;

  const [imageLoadError, setImageLoadError] = useState(false);
  const hasGenResult = !!app.generatedImageUrl && !imageLoadError;
  const genAfterScore = app.afterScore;

  const [streamedFact, setStreamedFact] = useState('');
  const [storageModalOpen, setStorageModalOpen] = useState(false);
  const [showNoCredits, setShowNoCredits] = useState(false);

  const [currentFact, setCurrentFact] = useState(() => PERCEPTION_FACTS.social[0]);
  const factIdxRef = useRef(0);
  const factTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoStartedRef = useRef(false);
  const [frozenStyle, setFrozenStyle] = useState<{ name: string; score: number } | null>(null);
  const [genFailed, setGenFailed] = useState(false);

  const isRunning = app.isGenerating && !hasGenResult;
  const progress = parseTaskProgress(app.currentTask?.status);

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
    }, 5000);
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
    }, 25);
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
      setShowNoCredits(true);
      return;
    }

    setGenFailed(false);
    setFrozenStyle({ name: selectedStyle.name, score: predictedAfterScore ?? 7.0 });
    await app.generate(undefined, effectiveStyle);
  }

  useEffect(() => {
    if (app.photo && !autoStartedRef.current && !hasGenResult && !app.isGenerating && !genFailed) {
      autoStartedRef.current = true;
      handleGenerate();
    }
  }, [app.photo]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleShare() {
    const res = await app.share();
    if (!res) return;
    if (navigator.share) {
      navigator.share({ title: 'AI Look Studio', text: res.caption, url: res.deep_link }).catch(() => {});
    } else {
      window.open(res.deep_link, '_blank');
    }
  }

  async function handleImproveFromStorage(imageUrl: string) {
    try {
      const res = await fetch(imageUrl, { credentials: 'omit' });
      const blob = await res.blob();
      const file = new File([blob], 'improve.jpg', { type: blob.type || 'image/jpeg' });
      app.uploadPhoto(file);
      setStorageModalOpen(false);
      onGoToStep('upload');
    } catch {
      /* ignore fetch errors */
    }
  }

  function goToPricing() {
    setShowNoCredits(false);
    navigate('/#тарифы');
  }

  return (
    <div className="flex flex-col gap-[var(--space-24)] w-full max-w-[800px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
        <h2 className="text-[24px] tablet:text-[32px] leading-[1.2] font-semibold text-[#E6EEF8]">
          {hasGenResult ? 'Результат готов' : isRunning ? 'Генерация...' : genFailed ? 'Ошибка генерации' : 'Генерация'}
        </h2>
        <p className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] max-w-[440px]">
          {hasGenResult
            ? 'AI улучшил ваше фото в выбранном стиле. Сравните результат с оригиналом.'
            : 'AI генерирует улучшенное фото в выбранном стиле. Это займёт несколько секунд.'}
        </p>
      </div>

      {/* Counters */}
      <div className="flex items-center justify-center gap-[var(--space-24)]">
        <div className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)]">
          <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
          <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">Баланс {app.balance}</span>
        </div>
        <button
          onClick={() => setStorageModalOpen(true)}
          className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)] cursor-pointer"
        >
          <ImageIcon size={16} className="text-[var(--color-brand-primary)]" />
          <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">Хранилище {app.taskHistoryCount}</span>
        </button>
      </div>

      {/* Before / After cards */}
      <div className="flex flex-col tablet:flex-row gap-[var(--space-16)] tablet:gap-[var(--space-32)] justify-center">
        {/* Original photo card */}
        <div className="gradient-border-card glass-card flex flex-col w-full tablet:w-[260px] rounded-[var(--radius-12)] overflow-hidden">
          <div className="w-full aspect-[3/4] tablet:h-[347px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
            {app.photo ? (
              <img src={app.photo.preview} alt="Original" className="w-full h-full object-cover" />
            ) : (
              <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
            )}
          </div>
          <div className="flex flex-col gap-[var(--space-8)] p-[var(--space-12)]">
            <div className="flex items-center justify-between">
              <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">Исходное</span>
              {beforeScore != null && (
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">{beforeScore.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              )}
            </div>
            {beforeScore != null && <ProgressBar value={beforeScore} />}
          </div>
        </div>

        {/* Generated photo card */}
        <div className="gradient-border-card glass-card flex flex-col w-full tablet:w-[260px] rounded-[var(--radius-12)] overflow-hidden">
          <div className="w-full aspect-[3/4] tablet:h-[347px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden relative">
            {hasGenResult && (
              <img
                src={app.generatedImageUrl!}
                alt="Generated"
                className="w-full h-full object-cover cursor-pointer"
                onClick={() => setStorageModalOpen(true)}
                onError={() => setImageLoadError(true)}
              />
            )}
            {imageLoadError && app.generatedImageUrl && (
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
            {/* Real generation in progress */}
            {!hasGenResult && isRunning && (
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
            {!hasGenResult && genFailed && !isRunning && (
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
            {!hasGenResult && !isRunning && !genFailed && (
              <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50" />
            )}
          </div>
          <div className="flex flex-col gap-[var(--space-8)] p-[var(--space-12)]">
            <div className="flex items-center justify-between">
              <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">
                {hasGenResult ? selectedStyle.name
                  : frozenStyle ? frozenStyle.name
                  : app.photo ? selectedStyle.name
                  : 'Апгрейд'}
              </span>
              {genAfterScore != null ? (
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">{genAfterScore.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              ) : frozenStyle ? (
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">~{frozenStyle.score.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              ) : predictedAfterScore != null ? (
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">~{predictedAfterScore.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              ) : null}
            </div>
            {isRunning ? (
              <ProgressBar value={progress?.percent ?? 10} max={100} accent />
            ) : genAfterScore != null ? (
              <ProgressBar value={genAfterScore} accent />
            ) : frozenStyle ? (
              <ProgressBar value={frozenStyle.score} accent />
            ) : predictedAfterScore != null ? (
              <ProgressBar value={predictedAfterScore} accent />
            ) : null}
          </div>
        </div>
      </div>

      {/* Fact streaming */}
      {isRunning && (
        <p className="text-[13px] leading-[18px] text-[var(--color-text-secondary)] italic text-center">
          {streamedFact}
          <span className="inline-block w-[2px] h-[13px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" />
        </p>
      )}

      {/* CTA buttons */}
      <div className="flex flex-col items-center gap-[var(--space-12)]">
        {hasGenResult && (
          <div className="flex flex-wrap gap-[var(--space-12)] justify-center">
            <button
              onClick={() => onGoToStep('style')}
              className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
            >
              Другой стиль
            </button>
            <button
              onClick={() => {
                app.resetGeneration();
                setFrozenStyle(null);
                onGoToStep('upload');
              }}
              className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
            >
              Другое фото
            </button>
            <button
              onClick={handleGenerate}
              disabled={app.isGenerating}
              className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Улучшить ещё
            </button>
            <button
              onClick={handleShare}
              className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
            >
              Поделиться
            </button>
          </div>
        )}
        {genFailed && !isRunning && !hasGenResult && (
          <button
            onClick={() => { app.clearError(); autoStartedRef.current = false; setGenFailed(false); handleGenerate(); }}
            className="glass-btn-primary px-[var(--space-32)] py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)]"
          >
            Повторить генерацию
          </button>
        )}
      </div>

      <StorageModal
        open={storageModalOpen}
        onClose={() => setStorageModalOpen(false)}
        items={app.taskHistory}
        onImprove={handleImproveFromStorage}
      />

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
    </div>
  );
}
