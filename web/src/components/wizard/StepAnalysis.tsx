import { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import { SIM_TEXTS, PARAM_LABELS, computeStyleDeltas } from './shared';
import { STYLES_BY_CATEGORY } from '../../data/styles';

interface Props {
  onNext: () => void;
}

export default function StepAnalysis({ onNext }: Props) {
  const app = useApp();
  const [analysisRequested, setAnalysisRequested] = useState(false);
  const [simStep, setSimStep] = useState(0);
  const [streamedText, setStreamedText] = useState('');

  const activeTab = app.activeCategory;
  const styles = STYLES_BY_CATEGORY[activeTab];
  const selectedStyle = styles.find(s => s.key === app.selectedStyleKey) ?? styles[0];

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : 5.99;
  const beforePerception = hasRealScores ? app.preAnalysis!.perception_scores : null;

  const displayParams = beforePerception
    ? Object.entries(beforePerception)
        .filter(([k]) => k !== 'authenticity')
        .map(([k, v]) => ({
          key: k,
          label: PARAM_LABELS[k] ?? k,
          before: v as number,
          after: app.afterPerception?.[k] ?? null,
        }))
    : null;

  const styleDelta = selectedStyle ? computeStyleDeltas(selectedStyle, activeTab) : null;

  function handleStartAnalysis() {
    if (!app.photo) return;
    setAnalysisRequested(true);
    setSimStep(0);
    setStreamedText('');
    app.startSimulation();
    app.runPreAnalyze();
  }

  useEffect(() => {
    if (!app.photo) {
      setSimStep(0);
      setStreamedText('');
      setAnalysisRequested(false);
    }
  }, [app.photo]);

  useEffect(() => {
    if (app.photo && !analysisRequested && !app.preAnalysis && !app.simulationDone) {
      handleStartAnalysis();
    }
  }, [app.photo]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!app.isSimulating) return;
    setSimStep(1);
    const t2 = setTimeout(() => setSimStep(2), 2000);
    const t3 = setTimeout(() => setSimStep(3), 4000);
    return () => { clearTimeout(t2); clearTimeout(t3); };
  }, [app.isSimulating]);

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

  return (
    <div className="flex flex-col gap-[var(--space-24)] w-full max-w-[800px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
        <h2 className="text-[24px] tablet:text-[32px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Анализ восприятия
        </h2>
        <p className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] max-w-[440px]">
          AI оценивает ваше фото по параметрам психологии восприятия: теплота, уверенность, привлекательность
        </p>
      </div>

      <div className="flex flex-col tablet:flex-row gap-[var(--space-24)] tablet:gap-[var(--space-32)]">
        {/* Photo card with score */}
        <div className="gradient-border-card glass-card flex flex-col w-full tablet:w-[260px] shrink-0 rounded-[var(--radius-12)] overflow-hidden">
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
              {app.photo && (
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">{beforeScore.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                </span>
              )}
            </div>
            {app.photo && <ProgressBar value={beforeScore} />}
          </div>
        </div>

        {/* Analysis panel */}
        <div className="flex-1 flex flex-col gap-[var(--space-16)]">
          {/* Description text */}
          <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] min-h-[40px]">
            {app.preAnalysis?.first_impression
              || (app.photo && analysisRequested && (app.isSimulating || app.simulationDone) && !app.preAnalysis ? (
                <>{streamedText}<span className="inline-block w-[2px] h-[14px] bg-[var(--color-brand-primary)] ml-[2px] align-middle animate-pulse" /></>
              ) : SIM_TEXTS[0])}
          </p>

          {/* Analysis button */}
          {app.photo && !analysisRequested && (
            <button
              onClick={handleStartAnalysis}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium"
            >
              Запустить анализ
            </button>
          )}

          {/* Streaming analysis (waiting for result) */}
          {analysisRequested && !app.preAnalysis && app.isSimulating && (
            <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-20)]">
              {[
                { step: 1, label: 'Анализ лица...' },
                { step: 2, label: 'Оценка параметров...' },
                { step: 3, label: 'Формирование результата...' },
              ].map((s) => (
                <div key={s.step} className="flex items-center gap-[var(--space-12)] transition-opacity duration-500" style={{ opacity: simStep >= s.step ? 1 : 0.2 }}>
                  {simStep > s.step ? (
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="9" fill="rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.15)"/><path d="M5.5 9.5L7.5 11.5L12.5 6.5" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  ) : simStep === s.step ? (
                    <div className="w-[18px] h-[18px] border-2 border-t-transparent rounded-full animate-spin shrink-0" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                  ) : (
                    <div className="w-[18px] h-[18px] rounded-full border border-[rgba(255,255,255,0.1)]" />
                  )}
                  <span className={`text-[14px] leading-[20px] ${simStep >= s.step ? 'text-[#E6EEF8]' : 'text-[var(--color-text-muted)]'}`}>{s.label}</span>
                </div>
              ))}
              <div className="h-1.5 rounded-full glass-progress-track overflow-hidden mt-[var(--space-4)]">
                <div className="h-full rounded-full glass-progress-fill transition-all duration-1000 ease-out" style={{ width: `${Math.min(simStep * 33.3, 100)}%` }} />
              </div>
            </div>
          )}

          {/* Real results */}
          {analysisRequested && (
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
                }) : (
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

              {app.preAnalysis?.enhancement_opportunities && app.preAnalysis.enhancement_opportunities.length > 0 && (
                <div className="flex flex-col gap-[var(--space-4)]">
                  <span className="text-[12px] font-medium text-[var(--color-text-muted)]">Возможности улучшения:</span>
                  {app.preAnalysis.enhancement_opportunities.slice(0, 3).map((opp, i) => (
                    <span key={i} className="text-[12px] text-[var(--color-text-secondary)]">{'\u2022'} {opp}</span>
                  ))}
                </div>
              )}
            </>
          )}

          {/* No photo */}
          {!app.photo && (
            <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
              <div className="text-[14px] text-[var(--color-text-muted)] text-center py-[var(--space-12)]">
                Загрузите фото для анализа
              </div>
            </div>
          )}

          {/* Next button */}
          {hasRealScores && (
            <button
              onClick={onNext}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)]"
            >
              Выбрать стиль
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
