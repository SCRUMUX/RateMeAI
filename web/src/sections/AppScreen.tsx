import { useState, useRef, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronLeftIcon, ChevronRightIcon, CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { STYLES_BY_CATEGORY, PARAMS_BY_MODE, getMockDelta, type CategoryId, type StyleItem } from '../data/styles';
import { PERCEPTION_FACTS, getRandomFact } from '../data/ai-facts';
import CategoryTabs from '../components/CategoryTabs';
import StorageModal from '../components/StorageModal';
import { useApp } from '../context/AppContext';

type GenSimMode = 'demo' | 'no_credits' | 'real';

const STYLES_PER_PAGE = 8;

function ProgressBar({ value, max = 10, accent = false }: { value: number; max?: number; accent?: boolean }) {
  return (
    <div className="w-full h-1.5 rounded-full glass-progress-track overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${accent ? 'glass-progress-fill' : 'glass-progress-fill-muted'}`}
        style={{ width: `${(value / max) * 100}%` }}
      />
    </div>
  );
}

function computeStyleDeltas(style: StyleItem, tab: CategoryId): Record<string, number> {
  const avgDelta = (style.deltaRange[0] + style.deltaRange[1]) / 2;
  const params = PARAMS_BY_MODE[tab];
  const result: Record<string, number> = {};
  const primaryShare = 0.6;
  const othersShare = 0.4 / Math.max(params.length - 1, 1);
  for (const p of params) {
    result[p.key] = p.key === style.param
      ? +(avgDelta * primaryShare).toFixed(2)
      : +(avgDelta * othersShare).toFixed(2);
  }
  return result;
}

export default function AppScreen({ onOpenAuthModal }: { onOpenAuthModal?: () => void }) {
  const app = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoScrollRef = useRef<HTMLDivElement>(null);
  const styleScrollRef = useRef<HTMLDivElement>(null);
  const [activePhotoIdx, setActivePhotoIdx] = useState(0);
  const [page, setPage] = useState(0);

  const activeTab = app.activeCategory;
  const styles = STYLES_BY_CATEGORY[activeTab];
  const totalPages = Math.ceil(styles.length / STYLES_PER_PAGE);

  const clampedPage = Math.min(page, totalPages - 1);
  const pageStyles = styles.slice(clampedPage * STYLES_PER_PAGE, (clampedPage + 1) * STYLES_PER_PAGE);
  const half = Math.ceil(pageStyles.length / 2);
  const leftCol = pageStyles.slice(0, half);
  const rightCol = pageStyles.slice(half);

  const allPages = Array.from({ length: totalPages }, (_, p) => {
    const start = p * STYLES_PER_PAGE;
    return styles.slice(start, start + STYLES_PER_PAGE);
  });

  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];
  const selectedIdx = styles.indexOf(selectedStyle);

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : 5.99;
  const beforePerception = hasRealScores ? app.preAnalysis!.perception_scores : null;

  const [analysisRequested, setAnalysisRequested] = useState(false);
  const [movedToStorageModal, setMovedToStorageModal] = useState(false);
  const [streamedFact, setStreamedFact] = useState('');
  const [imageLoadError, setImageLoadError] = useState(false);
  const hasGenResult = !!app.generatedImageUrl && !imageLoadError;
  const genAfterScore = app.afterScore;

  const predictedDelta = (selectedStyle.deltaRange[0] + selectedStyle.deltaRange[1]) / 2;
  const predictedAfterScore = +(beforeScore + predictedDelta).toFixed(2);

  const paramLabels: Record<string, string> = {
    warmth: 'Теплота', presence: 'Уверенность', appeal: 'Привлекательность',
    trust: 'Доверие', competence: 'Компетентность', hireability: 'Найм',
    social_score: 'Social Score', dating_score: 'Dating Score',
    authenticity: 'Аутентичность',
  };

  const displayParams = beforePerception
    ? Object.entries(beforePerception)
        .filter(([k]) => k !== 'authenticity')
        .map(([k, v]) => ({
          key: k,
          label: paramLabels[k] ?? k,
          before: v as number,
          after: app.afterPerception?.[k] ?? null,
        }))
    : null;

  const styleDelta = selectedStyle ? computeStyleDeltas(selectedStyle, activeTab) : null;

  function handlePhotoScroll() {
    const el = photoScrollRef.current;
    if (!el) return;
    const idx = Math.round(el.scrollLeft / el.offsetWidth);
    setActivePhotoIdx(idx);
  }

  function handleStyleScroll() {
    const el = styleScrollRef.current;
    if (!el) return;
    const idx = Math.round(el.scrollLeft / el.offsetWidth);
    setPage(idx);
  }

  function handleTabChange(id: CategoryId) {
    if (app.generationMode && app.generationMode !== id) {
      app.resetGeneration();
      resetGenSim();
      setFrozenStyle(null);
      setMovedToStorageModal(true);
      setTimeout(() => setMovedToStorageModal(false), 3500);
    }
    app.setActiveCategory(id);
    app.setSelectedStyleKey('');
    setPage(0);
    setAnalysisRequested(false);
  }

  function handleStyleClick(key: string) {
    if (app.generatedImageUrl && key !== app.selectedStyleKey) {
      app.resetGeneration();
      resetGenSim();
      setFrozenStyle(null);
      setMovedToStorageModal(true);
      setTimeout(() => setMovedToStorageModal(false), 3500);
    }
    app.setSelectedStyleKey(key);
  }

  function handlePageChange(newPage: number) {
    setPage(newPage);
  }

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    app.uploadPhoto(f);
  }, [app]);

  const [storageModalOpen, setStorageModalOpen] = useState(false);
  const [simStep, setSimStep] = useState(0);
  const [streamedText, setStreamedText] = useState('');

  // Generation simulation state
  const [genSimulating, setGenSimulating] = useState(false);
  const [genSimProgress, setGenSimProgress] = useState(0);
  const [genSimElapsed, setGenSimElapsed] = useState(0);
  const [genSimDone, setGenSimDone] = useState(false);
  const [genSimParamIdx, setGenSimParamIdx] = useState(0);
  const [genSimMode, setGenSimMode] = useState<GenSimMode>('demo');
  const [currentFact, setCurrentFact] = useState(() => PERCEPTION_FACTS.social[0]);
  const genSimRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const factIdxRef = useRef(0);
  const [frozenStyle, setFrozenStyle] = useState<{ name: string; score: number } | null>(null);

  const FIXED_DURATION = 27;

  const GEN_SIM_STEPS = [
    'Загрузка нейросети...',
    'Анализ структуры лица...',
    'Подбор параметров стиля...',
    'Генерация вариантов...',
    'Оптимизация деталей...',
    'Финальная обработка...',
  ];

  const SIM_TEXTS: Record<number, string> = {
    0: 'AI анализирует ваше фото по ключевым параметрам восприятия. Каждый стиль адаптирует образ под конкретный контекст, улучшая целевые метрики.',
    1: 'Определяем ключевые черты лица и выражение...',
    2: 'Оцениваем параметры восприятия: теплота, уверенность, привлекательность...',
    3: 'Формируем персонализированные рекомендации...',
    4: 'Произведён анализ фото с точки зрения психологии восприятия. Подобраны оптимальные параметры улучшения для выбранного контекста.',
  };

  useEffect(() => {
    if (!app.photo) {
      setSimStep(0); setStreamedText(''); resetGenSim(); setFrozenStyle(null);
      setAnalysisRequested(false);
      return;
    }
    setAnalysisRequested(false);
    setSimStep(0);
    setStreamedText('');
    resetGenSim();
    setFrozenStyle(null);
  }, [app.photo]);

  function handleStartAnalysis() {
    if (!app.photo) return;
    setAnalysisRequested(true);
    setSimStep(0);
    setStreamedText('');
    app.startSimulation();
    if (app.isAuthenticated) {
      app.runPreAnalyze();
    }
  }

  function resetGenSim() {
    setGenSimulating(false);
    setGenSimProgress(0);
    setGenSimElapsed(0);
    setGenSimDone(false);
    setGenSimParamIdx(0);
    setGenSimMode('demo');
    if (genSimRef.current) { clearInterval(genSimRef.current); genSimRef.current = null; }
  }

  function startGenSimulation(mode: GenSimMode) {
    resetGenSim();
    setGenSimMode(mode);
    setFrozenStyle({ name: selectedStyle.name, score: predictedAfterScore });
    setGenSimulating(true);
    factIdxRef.current = 0;
    const categoryFacts = PERCEPTION_FACTS[activeTab];
    setCurrentFact(categoryFacts[0]);
    const start = Date.now();
    let lastFactChange = 0;

    genSimRef.current = setInterval(() => {
      const elapsed = (Date.now() - start) / 1000;
      setGenSimElapsed(Math.floor(elapsed));

      if (mode === 'demo' || mode === 'no_credits') {
        const progress = Math.min((elapsed / FIXED_DURATION) * 100, 100);
        setGenSimProgress(progress);
        setGenSimParamIdx(Math.min(Math.floor(elapsed / (FIXED_DURATION / GEN_SIM_STEPS.length)), GEN_SIM_STEPS.length - 1));
        if (elapsed >= FIXED_DURATION) {
          clearInterval(genSimRef.current!);
          genSimRef.current = null;
          setGenSimulating(false);
          setGenSimDone(true);
          setGenSimProgress(100);
        }
      } else {
        const progress = Math.min(95, 60 + 35 * (1 - Math.exp(-elapsed / 60)));
        setGenSimProgress(progress);
        const stepIdx = Math.floor(elapsed / 5) % GEN_SIM_STEPS.length;
        setGenSimParamIdx(stepIdx);
      }

      if (elapsed - lastFactChange >= 5) {
        lastFactChange = elapsed;
        const { fact, index } = getRandomFact(factIdxRef.current, activeTab);
        factIdxRef.current = index;
        setCurrentFact(fact);
      }
    }, 200);
  }

  useEffect(() => () => { if (genSimRef.current) clearInterval(genSimRef.current); }, []);

  // Step-by-step simulation timer
  useEffect(() => {
    if (!app.isSimulating) return;
    setSimStep(1);
    const t2 = setTimeout(() => setSimStep(2), 2000);
    const t3 = setTimeout(() => setSimStep(3), 4000);
    return () => { clearTimeout(t2); clearTimeout(t3); };
  }, [app.isSimulating]);

  // Streaming text effect per simulation step
  useEffect(() => {
    if (simStep === 0 && !app.simulationDone) { setStreamedText(''); return; }
    const targetKey = app.simulationDone ? 4 : simStep;
    const target = SIM_TEXTS[targetKey] ?? '';
    setStreamedText('');
    let idx = 0;
    const iv = setInterval(() => {
      idx++;
      setStreamedText(target.slice(0, idx));
      if (idx >= target.length) clearInterval(iv);
    }, 20);
    return () => clearInterval(iv);
  }, [simStep, app.simulationDone]);

  useEffect(() => {
    if (!currentFact?.text || (!genSimulating && !app.isGenerating)) {
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
  }, [currentFact, genSimulating, app.isGenerating]);

  async function handleGenerate() {
    if (!app.photo) {
      fileInputRef.current?.click();
      return;
    }
    const effectiveStyle = app.selectedStyleKey || styles[0]?.key || '';
    if (!app.selectedStyleKey && effectiveStyle) {
      app.setSelectedStyleKey(effectiveStyle);
    }

    if (!app.isAuthenticated) {
      startGenSimulation('demo');
      return;
    }

    if (app.balance <= 0) {
      startGenSimulation('no_credits');
      return;
    }

    await app.generate(() => startGenSimulation('real'), effectiveStyle);
  }

  useEffect(() => { setImageLoadError(false); }, [app.generatedImageUrl]);

  // Auto-finish 'real' simulation when result arrives or generation fails
  useEffect(() => {
    if (!genSimulating || genSimMode !== 'real') return;
    if (app.generatedImageUrl || (app.error && !app.isGenerating)) {
      if (genSimRef.current) { clearInterval(genSimRef.current); genSimRef.current = null; }
      setGenSimProgress(100);
      setGenSimParamIdx(GEN_SIM_STEPS.length - 1);
      setGenSimulating(false);
      setGenSimDone(true);
    }
  }, [app.generatedImageUrl, app.error, app.isGenerating, genSimulating, genSimMode]);

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
    } catch {
      /* ignore fetch errors */
    }
  }

  return (
    <section id="app" className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] tablet:gap-[var(--space-40)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[120px]">
      {/* Brand heading */}
      <div className="relative flex items-center justify-center gap-[var(--space-12)] tablet:gap-[var(--space-24)] w-full max-w-[1200px]">
        <div className="brand-glow-backdrop" />
        <div className="relative w-[60px] h-[60px] tablet:w-[100px] tablet:h-[100px] desktop:w-[140px] desktop:h-[140px] shrink-0 brand-glow-icon">
          <div className="absolute inset-0 rounded-[16px] tablet:rounded-[24px] desktop:rounded-[28px]" style={{ background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.4)' }} />
          <img src="/img/logo.png" alt="AI Look Studio" className="relative w-full h-full object-contain rounded-[16px] tablet:rounded-[24px] desktop:rounded-[28px]" style={{ mixBlendMode: 'lighten' }} />
        </div>
        <span className="brand-glow-text text-[36px] tablet:text-[72px] desktop:text-[120px] leading-[1] font-extrabold whitespace-nowrap">
          AI Look Studio
        </span>
      </div>

      {/* Hidden file input */}
      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />

      {/* Error toast */}
      {app.error && (
        <div className="glass-badge-danger fixed top-20 right-6 z-[200] max-w-[400px] p-[var(--space-16)] text-white rounded-[var(--radius-12)] text-[14px] leading-[20px] cursor-pointer"
          onClick={app.clearError}
        >
          {app.error}
        </div>
      )}

      <div className="w-full max-w-[1200px]">
        {/* Category tab bar */}
        <div className="flex items-center justify-center mb-[var(--space-16)] tablet:mb-[var(--space-24)] w-full">
          <CategoryTabs active={activeTab} onChange={handleTabChange} />
        </div>

        {/* Content area */}
        <div className="p-0 tablet:p-[var(--space-24)]">
          {/* Top area: photos + analysis */}
          <div className="flex flex-col tablet:flex-row gap-[var(--space-20)] tablet:gap-[var(--space-32)] mb-[var(--space-20)] tablet:mb-[var(--space-32)]">
            {/* Photo cards */}
            <div className="flex flex-row overflow-x-auto snap-x snap-mandatory scrollbar-hide tablet:overflow-x-visible tablet:snap-none gap-0 tablet:gap-[var(--space-32)] shrink-0"
              ref={photoScrollRef}
              onScroll={handlePhotoScroll}
            >
              {/* Original photo */}
              <div className="gradient-border-card glass-card flex flex-col w-full min-w-full snap-center tablet:w-[260px] tablet:min-w-0 tablet:h-[472px] rounded-[var(--radius-12)] overflow-hidden">
                <div className="w-full aspect-[3/4] tablet:aspect-auto tablet:w-[260px] tablet:h-[347px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
                  {app.photo ? (
                    <img src={app.photo.preview} alt="Original" className="w-full h-full object-cover" />
                  ) : (
                    <img src="/img/placeholder-upload.png" alt="" className="w-full h-full object-cover opacity-50" />
                  )}
                </div>
                <div className="flex flex-col justify-between flex-1 pt-[var(--space-12)] pb-[var(--space-16)] px-[var(--space-12)]">
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <div className="flex items-center justify-between">
                      <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">Исходное</span>
                      {app.photo && (
                        <span className="flex items-center gap-1">
                          <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">{beforeScore.toFixed(2)}</span>
                          <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                        </span>
                      )}
                    </div>
                    {app.photo && <ProgressBar value={beforeScore} />}
                  </div>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] text-[#E6EEF8] rounded-[var(--radius-pill)]"
                  >
                    {app.photo ? 'Заменить фото' : 'Загрузить фото'}
                  </button>
                </div>
              </div>

              {/* Generated photo */}
              <div className="gradient-border-card glass-card flex flex-col w-full min-w-full snap-center tablet:w-[260px] tablet:min-w-0 tablet:h-[472px] rounded-[var(--radius-12)] overflow-hidden">
                <div className="w-full aspect-[3/4] tablet:aspect-auto tablet:w-[260px] tablet:h-[347px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden relative">
                  {/* Real result */}
                  {hasGenResult && (
                    <img
                      src={app.generatedImageUrl!}
                      alt="Generated"
                      className="w-full h-full object-cover cursor-pointer"
                      onClick={() => setStorageModalOpen(true)}
                      onError={() => setImageLoadError(true)}
                    />
                  )}
                  {/* Image load error with retry */}
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
                  {/* Real generation spinner (only when no sim running) */}
                  {!hasGenResult && app.isGenerating && !genSimulating && (
                    <div className="w-full h-full flex items-center justify-center absolute inset-0 bg-[rgba(0,0,0,0.5)] z-10">
                      <div className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.5)', borderTopColor: 'transparent' }} />
                    </div>
                  )}
                  {/* Gen simulation: animated placeholder + overlay */}
                  {!hasGenResult && genSimulating && (
                    <>
                      <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50 gen-sim-pulse" />
                      <div className="absolute inset-0 z-10 flex flex-col items-center justify-end pb-[var(--space-16)] gap-[var(--space-8)]" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 60%)' }}>
                        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.6)', borderTopColor: 'transparent' }} />
                        <span className="text-[12px] leading-[16px] text-[#E6EEF8] font-medium text-center px-[var(--space-8)]">
                          {GEN_SIM_STEPS[genSimParamIdx]}
                        </span>
                        <div className="w-[80%] h-1 rounded-full glass-progress-track overflow-hidden">
                          <div className="h-full rounded-full glass-progress-fill transition-all duration-200" style={{ width: `${genSimProgress}%` }} />
                        </div>
                      </div>
                    </>
                  )}
                  {/* Gen simulation done: blurred mock result or error overlay */}
                  {!hasGenResult && genSimDone && (
                    <div className="w-full h-full relative">
                      <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover" style={{ filter: 'blur(16px) saturate(1.6) brightness(0.6)', transform: 'scale(1.1)' }} />
                      <div className="absolute inset-0" style={{ background: 'linear-gradient(135deg, rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.25) 0%, rgba(0,0,0,0.3) 100%)' }} />
                      {genSimMode === 'real' && app.error && (
                        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-[var(--space-8)] text-center px-[var(--space-12)]">
                          <svg width="32" height="32" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="14" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5"/><path d="M16 10v8M16 22h.01" stroke="#E6EEF8" strokeWidth="2" strokeLinecap="round"/></svg>
                          <span className="text-[13px] leading-[18px] text-[#E6EEF8] font-medium">Не удалось сгенерировать</span>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Default placeholder */}
                  {!hasGenResult && !genSimulating && !genSimDone && !app.isGenerating && (
                    <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover opacity-50" />
                  )}
                </div>
                <div className="flex flex-col justify-between flex-1 pt-[var(--space-12)] pb-[var(--space-16)] px-[var(--space-12)]">
                  <div className="flex flex-col gap-[var(--space-8)]">
                    <div className="flex items-center justify-between">
                      <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">
                        {hasGenResult ? selectedStyle.name
                          : (genSimulating || genSimDone) && frozenStyle ? frozenStyle.name
                          : app.photo ? selectedStyle.name
                          : 'Апгрейд'}
                      </span>
                      {genAfterScore != null ? (
                        <span className="flex items-center gap-1">
                          <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">{genAfterScore.toFixed(2)}</span>
                          <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                        </span>
                      ) : (genSimulating || genSimDone) && frozenStyle ? (
                        <span className="flex items-center gap-1">
                          <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">~{frozenStyle.score.toFixed(2)}</span>
                          <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                        </span>
                      ) : app.photo ? (
                        <span className="flex items-center gap-1">
                          <span className="text-[14px] leading-[20px] text-[var(--color-brand-primary)] font-semibold">~{predictedAfterScore.toFixed(2)}</span>
                          <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                        </span>
                      ) : null}
                    </div>
                    {genSimulating ? (
                      <ProgressBar value={genSimProgress} max={100} accent />
                    ) : genSimDone && frozenStyle ? (
                      <ProgressBar value={frozenStyle.score} accent />
                    ) : genAfterScore != null ? (
                      <ProgressBar value={genAfterScore} accent />
                    ) : app.photo ? (
                      <ProgressBar value={predictedAfterScore} accent />
                    ) : null}
                  </div>
                  {genSimDone && genSimMode === 'demo' ? (
                    <button
                      onClick={onOpenAuthModal}
                      className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
                    >
                      Зарегистрироваться
                    </button>
                  ) : genSimDone && genSimMode === 'no_credits' ? (
                    <button
                      onClick={() => {
                        resetGenSim();
                        document.getElementById('тарифы')?.scrollIntoView({ behavior: 'smooth' });
                      }}
                      className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
                    >
                      Пополнить баланс
                    </button>
                  ) : hasGenResult ? (
                    <div className="flex gap-[var(--space-8)]">
                      <button
                        onClick={handleGenerate}
                        disabled={app.isGenerating || genSimulating}
                        className="flex-1 glass-btn-ghost px-[var(--space-12)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Улучшить
                      </button>
                      <button
                        onClick={handleShare}
                        className="flex-1 glass-btn-primary px-[var(--space-12)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
                      >
                        Поделиться
                      </button>
                    </div>
                  ) : genSimDone && genSimMode === 'real' ? (
                    <button
                      onClick={() => { app.clearError(); resetGenSim(); handleGenerate(); }}
                      className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
                    >
                      Повторить генерацию
                    </button>
                  ) : (
                    <button
                      onClick={handleGenerate}
                      disabled={app.isGenerating || genSimulating || !app.photo || !hasRealScores}
                      className={`${hasRealScores ? 'glass-btn-primary' : 'glass-btn-ghost'} px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] disabled:opacity-40 disabled:cursor-not-allowed`}
                    >
                      {app.isGenerating || genSimulating ? 'Обработка...' : 'Улучшить'}
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Swipe dot indicators (mobile only) */}
            <div className="flex tablet:hidden items-center justify-center gap-[var(--space-8)] mt-[var(--space-8)]">
              {[0, 1].map((i) => (
                <button
                  key={i}
                  className={`w-2 h-2 rounded-full transition-colors ${activePhotoIdx === i ? 'bg-[rgb(var(--accent-r),var(--accent-g),var(--accent-b))]' : 'bg-[rgba(255,255,255,0.25)]'}`}
                  onClick={() => {
                    const el = photoScrollRef.current;
                    if (el) el.scrollTo({ left: i * el.offsetWidth, behavior: 'smooth' });
                  }}
                />
              ))}
            </div>

            {/* Analysis panel */}
            <div className="flex-1 flex flex-col gap-[var(--space-20)]">
              {/* Top group — pinned to top */}
              <div className="flex flex-col gap-[var(--space-16)]">
                {/* Counters */}
                <div className="flex items-center gap-[var(--space-24)]">
                  <div className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)]">
                    <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
                    <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">Баланс {app.balance}</span>
                  </div>
                  <button
                    onClick={() => setStorageModalOpen(true)}
                    className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)] cursor-pointer"
                  >
                    <ImageIcon size={16} className="text-[var(--color-brand-primary)]" />
                    <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">
                      Хранилище {app.taskHistoryCount}
                    </span>
                  </button>
                </div>

                {/* Section heading */}
                <div className="flex gap-[var(--space-16)]">
                  <div className="flex items-center gap-[var(--space-4)]">
                    <span className="text-[18px] font-semibold leading-[24px] text-[#E6EEF8]">Анализ восприятия</span>
                    <div className="glass-badge-cyan flex items-center gap-[var(--space-4)] px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)]">
                      <span className="text-[11px] leading-[14px] font-medium text-[#E6EEF8]">До</span>
                    </div>
                    <div className="glass-badge-success flex items-center gap-[var(--space-4)] px-[var(--space-8)] py-[2px] rounded-[var(--radius-pill)]">
                      <span className="text-[11px] leading-[14px] font-medium text-[#E6EEF8]">После</span>
                    </div>
                  </div>
                </div>

                <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] max-w-[440px] min-h-[40px]">
                  {app.preAnalysis?.first_impression
                    || (app.photo && analysisRequested && (app.isSimulating || app.simulationDone) && !app.preAnalysis ? (
                      <>{streamedText}<span className="inline-block w-[2px] h-[14px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" /></>
                    ) : SIM_TEXTS[0])}
                </p>

                {/* Analysis button — shown when photo loaded but analysis not started */}
                {app.photo && !analysisRequested && (
                  <button
                    onClick={handleStartAnalysis}
                    className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium"
                  >
                    Запустить анализ
                  </button>
                )}

                {/* === STATE 1: Simulating analysis (not authenticated, photo uploaded) === */}
                {app.photo && !app.isAuthenticated && analysisRequested && app.isSimulating && (
                  <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-20)]">
                    {[
                      { step: 1, label: 'Анализ лица...' },
                      { step: 2, label: 'Оценка параметров...' },
                      { step: 3, label: 'Формирование результата...' },
                    ].map((s) => (
                      <div
                        key={s.step}
                        className="flex items-center gap-[var(--space-12)] transition-opacity duration-500"
                        style={{ opacity: simStep >= s.step ? 1 : 0.2 }}
                      >
                        {simStep > s.step ? (
                          <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.15)"/><path d="M5.5 9.5L7.5 11.5L12.5 6.5" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        ) : simStep === s.step ? (
                          <div className="w-[18px] h-[18px] border-2 border-t-transparent rounded-full animate-spin shrink-0" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                        ) : (
                          <div className="w-[18px] h-[18px] rounded-full border border-[rgba(255,255,255,0.1)]" />
                        )}
                        <span className={`text-[14px] leading-[20px] ${simStep >= s.step ? 'text-[#E6EEF8]' : 'text-[var(--color-text-muted)]'}`}>
                          {s.label}
                        </span>
                      </div>
                    ))}
                    <div className="h-1.5 rounded-full glass-progress-track overflow-hidden mt-[var(--space-4)]">
                      <div
                        className="h-full rounded-full glass-progress-fill transition-all duration-1000 ease-out"
                        style={{ width: `${Math.min(simStep * 33.3, 100)}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* === STATE 2: Blurred fake results + CTA (simulation done, not authenticated) === */}
                {app.photo && !app.isAuthenticated && analysisRequested && app.simulationDone && (
                  <div className="relative">
                    <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]" style={{ filter: 'blur(6px)' }}>
                      {PARAMS_BY_MODE[activeTab].map((p) => (
                        <div key={p.key} className="flex flex-col gap-[var(--space-8)]">
                          <div className="flex items-center justify-between">
                            <span className="text-[14px] leading-[20px] text-[#E6EEF8]">{p.label}</span>
                            <span className="flex items-center gap-[var(--space-8)] text-[14px] leading-[20px] tabular-nums">
                              <span className="text-[var(--color-text-muted)]">{p.before.toFixed(2)}</span>
                              <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                            </span>
                          </div>
                          <ProgressBar value={p.before} />
                        </div>
                      ))}
                    </div>
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-[var(--space-12)] rounded-[var(--radius-12)]">
                      <span className="text-[18px] font-semibold leading-[24px] text-[#E6EEF8]">Результаты готовы</span>
                      <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] text-center max-w-[300px]">
                        Зарегистрируйтесь, чтобы увидеть полный анализ восприятия
                      </span>
                      <button
                        onClick={onOpenAuthModal}
                        className="glass-btn-primary px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)]"
                      >
                        Получить доступ
                      </button>
                    </div>
                  </div>
                )}

                {/* === STATE 3a: Streaming analysis (authenticated, waiting for result) === */}
                {app.isAuthenticated && analysisRequested && !app.preAnalysis && app.isSimulating && (
                  <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-20)]">
                    {[
                      { step: 1, label: 'Анализ лица...' },
                      { step: 2, label: 'Оценка параметров...' },
                      { step: 3, label: 'Формирование результата...' },
                    ].map((s) => (
                      <div
                        key={s.step}
                        className="flex items-center gap-[var(--space-12)] transition-opacity duration-500"
                        style={{ opacity: simStep >= s.step ? 1 : 0.2 }}
                      >
                        {simStep > s.step ? (
                          <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.15)"/><path d="M5.5 9.5L7.5 11.5L12.5 6.5" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        ) : simStep === s.step ? (
                          <div className="w-[18px] h-[18px] border-2 border-t-transparent rounded-full animate-spin shrink-0" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                        ) : (
                          <div className="w-[18px] h-[18px] rounded-full border border-[rgba(255,255,255,0.1)]" />
                        )}
                        <span className={`text-[14px] leading-[20px] ${simStep >= s.step ? 'text-[#E6EEF8]' : 'text-[var(--color-text-muted)]'}`}>
                          {s.label}
                        </span>
                      </div>
                    ))}
                    <div className="h-1.5 rounded-full glass-progress-track overflow-hidden mt-[var(--space-4)]">
                      <div
                        className="h-full rounded-full glass-progress-fill transition-all duration-1000 ease-out"
                        style={{ width: `${Math.min(simStep * 33.3, 100)}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* === STATE 3: Real results (authenticated) === */}
                {app.isAuthenticated && analysisRequested && (
                  <>
                    <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                      {displayParams ? displayParams.map((p) => {
                        const after = p.after;
                        const d = after != null ? +(after - p.before).toFixed(2) : null;
                        const predicted = styleDelta?.[p.key] ?? null;
                        return (
                          <div key={p.key} className="flex flex-col gap-[var(--space-8)]">
                            <div className="flex items-center justify-between">
                              <span className="text-[14px] leading-[20px] text-[#E6EEF8]">{p.label}</span>
                              <span className="flex items-center gap-[var(--space-8)] text-[14px] leading-[20px] tabular-nums">
                                <span className="text-[var(--color-text-muted)]">{p.before.toFixed(2)}</span>
                                {after != null && (
                                  <>
                                    <span className="text-[var(--color-text-muted)]">{'\u2192'}</span>
                                    <span className="text-[var(--color-brand-primary)] font-semibold">{after.toFixed(2)}</span>
                                    <span className="text-[var(--color-success-base)] text-[12px]">(+{d!.toFixed(2)})</span>
                                  </>
                                )}
                                {after == null && predicted != null && predicted > 0 && (
                                  <span className="text-[var(--color-success-base)] text-[12px] font-medium">+{predicted.toFixed(2)}</span>
                                )}
                                {after == null && !predicted && <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>}
                              </span>
                            </div>
                            <div className="relative">
                              <ProgressBar value={p.before} />
                              {after != null && (
                                <div className="absolute inset-0"><ProgressBar value={after} accent /></div>
                              )}
                            </div>
                          </div>
                        );
                      }                      ) : (
                        <div className="flex flex-col items-center gap-[var(--space-8)] text-center py-[var(--space-12)]">
                          {app.preAnalyzeError ? (
                            <>
                              <span className="text-[14px] text-[var(--color-text-muted)]">Не удалось загрузить анализ</span>
                              <button
                                onClick={() => { app.runPreAnalyze(); }}
                                className="glass-btn-ghost px-[var(--space-16)] py-[var(--space-6)] text-[13px] text-[#E6EEF8] rounded-[var(--radius-pill)]"
                              >
                                Повторить
                              </button>
                            </>
                          ) : app.photo ? (
                            <div className="flex items-center gap-[var(--space-8)]">
                              <div className="w-4 h-4 border-2 border-t-transparent rounded-full animate-spin shrink-0" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                              <span className="text-[14px] text-[var(--color-text-muted)]">Анализируем...</span>
                            </div>
                          ) : (
                            <span className="text-[14px] text-[var(--color-text-muted)]">Загрузите фото для анализа</span>
                          )}
                        </div>
                      )}
                    </div>

                    {(genSimulating || (app.isGenerating && !genSimDone)) && (
                      <p className="text-[13px] leading-[18px] text-[var(--color-text-secondary)] italic">
                        {streamedFact}
                        <span className="inline-block w-[2px] h-[13px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" />
                      </p>
                    )}

                    {app.preAnalysis?.enhancement_opportunities && app.preAnalysis.enhancement_opportunities.length > 0 && !genSimulating && !(app.isGenerating && !genSimDone) && (
                      <div className="flex flex-col gap-[var(--space-4)]">
                        <span className="text-[12px] font-medium text-[var(--color-text-muted)]">Возможности улучшения:</span>
                        {app.preAnalysis.enhancement_opportunities.slice(0, 3).map((opp, i) => (
                          <span key={i} className="text-[12px] text-[var(--color-text-secondary)]">{'\u2022'} {opp}</span>
                        ))}
                      </div>
                    )}
                  </>
                )}

                {/* === STATE 0: No photo uploaded === */}
                {!app.photo && (
                  <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                    <div className="text-[14px] text-[var(--color-text-muted)] text-center py-[var(--space-12)]">
                      Загрузите фото для анализа
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Style list — mobile: all pages as horizontal swipe; tablet+: two-column for current page */}

          {/* Mobile: swipeable pages */}
          <div
            ref={styleScrollRef}
            onScroll={handleStyleScroll}
            className="flex tablet:hidden flex-row overflow-x-auto snap-x snap-mandatory scrollbar-hide"
          >
            {allPages.map((pageItems, pageIdx) => (
              <div key={pageIdx} className="w-full min-w-full snap-center flex flex-col gap-[var(--space-12)]">
                {pageItems.map((s) => {
                  const gIdx = styles.indexOf(s);
                  return (
                    <div key={s.key}
                      onClick={() => handleStyleClick(s.key)}
                      className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all ${
                        selectedIdx === gIdx ? 'glass-row-active' : 'glass-row'
                      }`}
                      style={{ '--gb-color': selectedIdx === gIdx ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)' : 'rgba(255, 255, 255, 0.10)' } as React.CSSProperties}
                    >
                      <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
                      <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                        <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
                        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
                      </div>
                      <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                        {getMockDelta(s.deltaRange, s.key)}
                      </span>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          {/* Mobile: page indicators */}
          {totalPages > 1 && (
            <div className="flex tablet:hidden items-center justify-center gap-[6px] mt-[var(--space-8)]">
              {allPages.map((_, i) => (
                <button
                  key={i}
                  className={`w-2 h-2 rounded-full transition-colors ${clampedPage === i ? 'bg-[rgb(var(--accent-r),var(--accent-g),var(--accent-b))]' : 'bg-[rgba(255,255,255,0.25)]'}`}
                  onClick={() => {
                    const el = styleScrollRef.current;
                    if (el) el.scrollTo({ left: i * el.offsetWidth, behavior: 'smooth' });
                  }}
                />
              ))}
            </div>
          )}

          {/* Tablet+: two-column layout for current page */}
          <div className="hidden tablet:flex flex-row gap-[var(--space-32)]">
            <div className="flex-1 flex flex-col gap-[var(--space-12)]">
              {leftCol.map((s) => {
                const gIdx = styles.indexOf(s);
                return (
                  <div key={s.key}
                    onClick={() => handleStyleClick(s.key)}
                    className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all ${
                      selectedIdx === gIdx ? 'glass-row-active' : 'glass-row'
                    }`}
                    style={{ '--gb-color': selectedIdx === gIdx ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)' : 'rgba(255, 255, 255, 0.10)' } as React.CSSProperties}
                  >
                    <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
                    <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                      <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
                    </div>
                    <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                      {getMockDelta(s.deltaRange, s.key)}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="flex-1 flex flex-col gap-[var(--space-12)]">
              {rightCol.map((s) => {
                const gIdx = styles.indexOf(s);
                return (
                  <div key={s.key}
                    onClick={() => handleStyleClick(s.key)}
                    className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all ${
                      selectedIdx === gIdx ? 'glass-row-active' : 'glass-row'
                    }`}
                    style={{ '--gb-color': selectedIdx === gIdx ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)' : 'rgba(255, 255, 255, 0.10)' } as React.CSSProperties}
                  >
                    <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
                    <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                      <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
                      <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
                    </div>
                    <span className="px-[var(--space-8)] py-[var(--space-4)] rounded-[var(--radius-pill)] text-[14px] leading-[20px] text-[var(--color-success-base)] font-medium tabular-nums shrink-0">
                      {getMockDelta(s.deltaRange, s.key)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Pagination — tablet+ only */}
          {totalPages > 1 && (
            <div className="hidden tablet:flex items-center justify-center gap-[var(--space-12)] mt-[var(--space-16)] tablet:mt-[var(--space-32)]">
              <button
                onClick={() => handlePageChange(Math.max(0, clampedPage - 1))}
                disabled={clampedPage === 0}
                className="glass-btn-ghost w-10 h-10 flex items-center justify-center rounded-[var(--radius-12)] text-[var(--color-text-muted)] hover:text-[#E6EEF8]"
              >
                <ChevronLeftIcon size={20} />
              </button>
              <span className="text-[14px] leading-[20px] text-[#E6EEF8] tabular-nums">
                {clampedPage + 1} / {totalPages}
              </span>
              <button
                onClick={() => handlePageChange(Math.min(totalPages - 1, clampedPage + 1))}
                disabled={clampedPage === totalPages - 1}
                className="glass-btn-ghost w-10 h-10 flex items-center justify-center rounded-[var(--radius-12)] text-[var(--color-text-muted)] hover:text-[#E6EEF8]"
              >
                <ChevronRightIcon size={20} />
              </button>
            </div>
          )}
        </div>
      </div>

      <StorageModal
        open={storageModalOpen}
        onClose={() => setStorageModalOpen(false)}
        items={app.taskHistory}
        onImprove={handleImproveFromStorage}
      />

      <AnimatePresence>
        {movedToStorageModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setMovedToStorageModal(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.25 }}
              className="glass-card rounded-[var(--radius-16)] p-[var(--space-24)] max-w-sm w-full mx-4 flex flex-col items-center gap-[var(--space-16)] text-center"
              onClick={(e) => e.stopPropagation()}
            >
              <ImageIcon size={40} className="text-[var(--color-brand-primary)]" />
              <p className="text-[16px] font-semibold text-[#E6EEF8]">
                Сгенерированное фото перемещено в хранилище
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {app.noCreditsError && (
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
                onClick={() => app.clearNoCreditsError()}
              >
                Закрыть
              </button>
              <button
                className="flex-1 glass-btn-primary rounded-[var(--radius-12)] py-[var(--space-10)] text-[14px] font-semibold text-white"
                onClick={() => {
                  app.clearNoCreditsError();
                  document.getElementById('тарифы')?.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                Пополнить баланс
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
