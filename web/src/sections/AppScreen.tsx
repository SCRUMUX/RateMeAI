import { useState, useRef, useEffect, useCallback, type SyntheticEvent } from 'react';
import { AicaIcon, ChevronLeftIcon, ChevronRightIcon, CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { STYLES_BY_CATEGORY, PARAMS_BY_MODE, getMockDelta, type CategoryId } from '../data/styles';
import CategoryTabs from '../components/CategoryTabs';
import AuthModal from '../components/AuthModal';
import { useApp } from '../context/AppContext';

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

export default function AppScreen() {
  const app = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [page, setPage] = useState(0);

  const activeTab = app.activeCategory;
  const styles = STYLES_BY_CATEGORY[activeTab];
  const totalPages = Math.ceil(styles.length / STYLES_PER_PAGE);

  const clampedPage = Math.min(page, totalPages - 1);
  const pageStyles = styles.slice(clampedPage * STYLES_PER_PAGE, (clampedPage + 1) * STYLES_PER_PAGE);
  const half = Math.ceil(pageStyles.length / 2);
  const leftCol = pageStyles.slice(0, half);
  const rightCol = pageStyles.slice(half);

  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];
  const selectedIdx = styles.indexOf(selectedStyle);

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : 5.99;
  const beforePerception = hasRealScores ? app.preAnalysis!.perception_scores : null;

  const hasGenResult = !!app.generatedImageUrl;
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

  function handleTabChange(id: CategoryId) {
    app.setActiveCategory(id);
    app.setSelectedStyleKey('');
    setPage(0);
    if (app.photo) app.runPreAnalyze();
  }

  function handleStyleClick(key: string) {
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

  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [simStep, setSimStep] = useState(0);
  const [streamedText, setStreamedText] = useState('');

  // Generation simulation state
  const [genSimulating, setGenSimulating] = useState(false);
  const [genSimProgress, setGenSimProgress] = useState(0);
  const [genSimElapsed, setGenSimElapsed] = useState(0);
  const [genSimDone, setGenSimDone] = useState(false);
  const [genSimParamIdx, setGenSimParamIdx] = useState(0);
  const genSimRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [frozenStyle, setFrozenStyle] = useState<{ name: string; score: number } | null>(null);

  const GEN_DURATION = 27;

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

  // When photo uploaded or replaced: restart analysis from scratch
  useEffect(() => {
    if (!app.photo) { setSimStep(0); setStreamedText(''); resetGenSim(); setFrozenStyle(null); return; }
    if (app.isAuthenticated) {
      app.runPreAnalyze();
    } else {
      app.startSimulation();
      setSimStep(0);
      setStreamedText('');
      resetGenSim();
      setFrozenStyle(null);
    }
  }, [app.photo]);

  function resetGenSim() {
    setGenSimulating(false);
    setGenSimProgress(0);
    setGenSimElapsed(0);
    setGenSimDone(false);
    setGenSimParamIdx(0);
    if (genSimRef.current) { clearInterval(genSimRef.current); genSimRef.current = null; }
  }

  function startGenSimulation() {
    resetGenSim();
    setFrozenStyle({ name: selectedStyle.name, score: predictedAfterScore });
    setGenSimulating(true);
    const start = Date.now();
    genSimRef.current = setInterval(() => {
      const elapsed = (Date.now() - start) / 1000;
      const progress = Math.min((elapsed / GEN_DURATION) * 100, 100);
      setGenSimElapsed(Math.floor(elapsed));
      setGenSimProgress(progress);
      setGenSimParamIdx(Math.min(Math.floor(elapsed / (GEN_DURATION / GEN_SIM_STEPS.length)), GEN_SIM_STEPS.length - 1));
      if (elapsed >= GEN_DURATION) {
        clearInterval(genSimRef.current!);
        genSimRef.current = null;
        setGenSimulating(false);
        setGenSimDone(true);
        setGenSimProgress(100);
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

  async function handleGenerate() {
    if (!app.photo) {
      fileInputRef.current?.click();
      return;
    }
    if (!app.selectedStyleKey) {
      app.setSelectedStyleKey(styles[0]?.key ?? '');
    }
    if (!app.isAuthenticated) {
      startGenSimulation();
      return;
    }
    startGenSimulation();
    await app.generate();
  }

  // Auto-finish simulation when real result arrives or generation fails
  useEffect(() => {
    if (!genSimulating) return;
    if (app.generatedImageUrl || (app.error && !app.isGenerating)) {
      if (genSimRef.current) { clearInterval(genSimRef.current); genSimRef.current = null; }
      setGenSimProgress(100);
      setGenSimParamIdx(GEN_SIM_STEPS.length - 1);
      setGenSimulating(false);
      setGenSimDone(true);
    }
  }, [app.generatedImageUrl, app.error, app.isGenerating, genSimulating]);

  async function handleShare() {
    const res = await app.share();
    if (!res) return;
    if (navigator.share) {
      navigator.share({ title: 'AI Look Studio', text: res.caption, url: res.deep_link }).catch(() => {});
    } else {
      window.open(res.deep_link, '_blank');
    }
  }

  return (
    <section id="app" className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] px-[var(--space-24)] py-[120px]">
      {/* Brand heading */}
      <div className="relative flex items-center justify-center gap-[var(--space-24)] w-full max-w-[1200px]">
        <div className="brand-glow-backdrop" />
        <AicaIcon size={128} className="brand-glow-icon text-[var(--color-brand-primary)] -rotate-45 shrink-0" />
        <span className="brand-glow-text text-[120px] leading-[1] font-extrabold whitespace-nowrap">
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
        <div className="flex items-center justify-center mb-[var(--space-24)]">
          <CategoryTabs active={activeTab} onChange={handleTabChange} />
        </div>

        {/* Content area */}
        <div className="p-[var(--space-24)]">
          {/* Top area: photos + analysis */}
          <div className="flex gap-[var(--space-32)] mb-[var(--space-32)]">
            {/* Photo cards */}
            <div className="flex gap-[70px] shrink-0">
              {/* Original photo */}
              <div className="gradient-border-card glass-card flex flex-col w-[236px] h-[440px] rounded-[var(--radius-12)] overflow-hidden">
                <div className="w-[236px] h-[315px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
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
              <div className="gradient-border-card glass-card flex flex-col w-[236px] h-[440px] rounded-[var(--radius-12)] overflow-hidden">
                <div className="w-[236px] h-[315px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden relative">
                  {/* Real result */}
                  {hasGenResult && (
                    <img
                      src={app.generatedImageUrl!}
                      alt="Generated"
                      className="w-full h-full object-cover"
                      onError={(e: SyntheticEvent<HTMLImageElement>) => {
                        e.currentTarget.style.display = 'none';
                        const parent = e.currentTarget.parentElement;
                        if (parent && !parent.querySelector('.img-error-msg')) {
                          const msg = document.createElement('div');
                          msg.className = 'img-error-msg w-full h-full flex items-center justify-center text-[14px] text-[var(--color-text-muted)] text-center p-4';
                          msg.textContent = 'Не удалось загрузить изображение';
                          parent.appendChild(msg);
                        }
                      }}
                    />
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
                        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] tabular-nums">
                          {genSimElapsed}с
                        </span>
                        <div className="w-[80%] h-1 rounded-full glass-progress-track overflow-hidden">
                          <div className="h-full rounded-full glass-progress-fill transition-all duration-200" style={{ width: `${genSimProgress}%` }} />
                        </div>
                      </div>
                    </>
                  )}
                  {/* Gen simulation done: blurred mock result */}
                  {!hasGenResult && genSimDone && (
                    <div className="w-full h-full relative">
                      <img src="/img/placeholder-upgrade.png" alt="" className="w-full h-full object-cover" style={{ filter: 'blur(16px) saturate(1.6) brightness(0.6)', transform: 'scale(1.1)' }} />
                      <div className="absolute inset-0" style={{ background: 'linear-gradient(135deg, rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.25) 0%, rgba(0,0,0,0.3) 100%)' }} />
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
                  {genSimDone && !app.isAuthenticated ? (
                    <button
                      onClick={() => setAuthModalOpen(true)}
                      className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)]"
                    >
                      Разблокировать доступ
                    </button>
                  ) : (
                    <button
                      onClick={hasGenResult ? handleShare : handleGenerate}
                      disabled={app.isGenerating || genSimulating || !app.photo}
                      className="glass-btn-primary px-[var(--space-20)] py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {app.isGenerating || genSimulating ? 'Обработка...' : hasGenResult ? 'Поделиться' : 'Улучшить'}
                    </button>
                  )}
                </div>
              </div>
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
                  <div className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)]">
                    <ImageIcon size={16} className="text-[var(--color-brand-primary)]" />
                    <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">
                      {app.session ? `Лимит ${app.session.usage.remaining}` : 'Хранилище'}
                    </span>
                  </div>
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
                    || (app.photo && !app.isAuthenticated && (app.isSimulating || app.simulationDone) ? (
                      <>{streamedText}<span className="inline-block w-[2px] h-[14px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" /></>
                    ) : SIM_TEXTS[0])}
                </p>
              </div>

              {/* Spacer pushes bottom group down */}
              <div className="flex-1" />

              {/* Bottom group — pinned to bottom of photo cards */}
              {/* === STATE 1: Simulating analysis (not authenticated, photo uploaded) === */}
              {app.photo && !app.isAuthenticated && app.isSimulating && (
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
              {app.photo && !app.isAuthenticated && app.simulationDone && (
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
                      onClick={() => setAuthModalOpen(true)}
                      className="glass-btn-primary px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[24px] rounded-[var(--radius-12)]"
                    >
                      Получить доступ
                    </button>
                  </div>
                </div>
              )}

              {/* === STATE 3: Real results (authenticated) === */}
              {app.isAuthenticated && (
                <>
                  <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                    {displayParams ? displayParams.map((p) => {
                      const after = p.after;
                      const d = after != null ? +(after - p.before).toFixed(2) : null;
                      return (
                        <div key={p.key} className="flex flex-col gap-[var(--space-8)]">
                          <div className="flex items-center justify-between">
                            <span className="text-[14px] leading-[20px] text-[#E6EEF8]">{p.label}</span>
                            <span className="flex items-center gap-[var(--space-8)] text-[14px] leading-[20px] tabular-nums">
                              <span className="text-[var(--color-text-muted)]">{p.before.toFixed(2)}</span>
                              {after != null && (
                                <>
                                  <span className="text-[var(--color-text-muted)]">→</span>
                                  <span className="text-[var(--color-brand-primary)] font-semibold">{after.toFixed(2)}</span>
                                  <span className="text-[var(--color-success-base)] text-[12px]">(+{d!.toFixed(2)})</span>
                                </>
                              )}
                              {after == null && <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>}
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
                    }) : (
                      <div className="text-[14px] text-[var(--color-text-muted)] text-center py-[var(--space-12)]">
                        {app.photo ? 'Анализируем...' : 'Загрузите фото для анализа'}
                      </div>
                    )}
                  </div>

                  {app.preAnalysis?.enhancement_opportunities && app.preAnalysis.enhancement_opportunities.length > 0 && (
                    <div className="flex flex-col gap-[var(--space-4)]">
                      <span className="text-[12px] font-medium text-[var(--color-text-muted)]">Возможности улучшения:</span>
                      {app.preAnalysis.enhancement_opportunities.slice(0, 3).map((opp, i) => (
                        <span key={i} className="text-[12px] text-[var(--color-text-secondary)]">• {opp}</span>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* === STATE 0: No photo uploaded === */}
              {!app.photo && !app.isAuthenticated && (
                <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                  <div className="text-[14px] text-[var(--color-text-muted)] text-center py-[var(--space-12)]">
                    Загрузите фото для анализа
                  </div>
                </div>
              )}
              {!app.photo && app.isAuthenticated && !displayParams && (
                <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                  <div className="text-[14px] text-[var(--color-text-muted)] text-center py-[var(--space-12)]">
                    Загрузите фото для анализа
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Style list - dual column */}
          <div className="flex gap-[var(--space-32)]">
            <div className="flex-1 flex flex-col gap-[var(--space-12)]">
              {leftCol.map((s) => {
                const gIdx = styles.indexOf(s);
                return (
                  <div key={s.key}
                    onClick={() => handleStyleClick(s.key)}
                    className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all ${
                      selectedIdx === gIdx
                        ? 'glass-row-active'
                        : 'glass-row'
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
                      selectedIdx === gIdx
                        ? 'glass-row-active'
                        : 'glass-row'
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

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-[var(--space-12)] mt-[var(--space-32)]">
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

      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onAuth={async (email) => {
          await app.authenticateUser(email);
          setAuthModalOpen(false);
        }}
        onOAuth={async (provider) => {
          await app.loginWithOAuth(provider);
        }}
      />
    </section>
  );
}
