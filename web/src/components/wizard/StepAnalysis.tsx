import { useState, useEffect, useMemo } from 'react';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import { PARAM_LABELS } from './shared';
import { STYLES_BY_CATEGORY } from '../../data/styles';

interface Props {
  onNext: () => void;
}

const DEFAULT_DESCRIPTION = 'AI анализирует ваше фото по ключевым параметрам восприятия. Каждый стиль адаптирует образ под конкретный контекст, улучшая целевые метрики.';
const DOC_DEFAULT_DESCRIPTION = 'AI анализирует ваше фото для проверки пригодности к использованию в документах. Оцениваются освещение, фон и расположение лица.';

export default function StepAnalysis({ onNext }: Props) {
  const app = useApp();
  const [analysisRequested, setAnalysisRequested] = useState(false);
  const isSimplified = app.scenarioSimplifiedAnalysis;

  const activeTab = app.activeCategory;

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : null;
  const beforePerception = hasRealScores ? app.preAnalysis!.perception_scores : null;

  const displayParams = beforePerception
    ? Object.entries(beforePerception)
        .filter(([k]) => k !== 'authenticity')
        .map(([k, v]) => ({
          key: k,
          label: PARAM_LABELS[k] ?? k,
          value: v as number,
        }))
    : null;

  const recommendation = useMemo(() => {
    if (!displayParams || displayParams.length === 0) return null;
    const weakest = displayParams.reduce((min, p) => p.value < min.value ? p : min, displayParams[0]);
    const styles = STYLES_BY_CATEGORY[activeTab];
    const matching = styles
      .filter(s => s.param === weakest.key)
      .sort((a, b) => (b.deltaRange[0] + b.deltaRange[1]) - (a.deltaRange[0] + a.deltaRange[1]))
      .slice(0, 2);
    if (matching.length === 0) return null;
    return { param: weakest, styles: matching };
  }, [displayParams, activeTab]);

  function handleStartAnalysis() {
    if (!app.photo) return;
    setAnalysisRequested(true);
    app.runPreAnalyze();
  }

  useEffect(() => {
    if (!app.photo) {
      setAnalysisRequested(false);
    }
  }, [app.photo]);

  useEffect(() => {
    if (app.photo && !analysisRequested && !app.preAnalysis && !app.preAnalyzeLoading) {
      handleStartAnalysis();
    }
  }, [app.photo]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col gap-[var(--space-12)] w-full max-w-[800px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-4)] text-center">
        <h2 className="text-[20px] tablet:text-[28px] leading-[1.2] font-semibold text-[#E6EEF8]">
          {isSimplified ? 'Анализ фото' : 'Анализ восприятия'}
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          {isSimplified
            ? 'AI проверяет пригодность фото для документов'
            : 'AI оценивает ваше фото по параметрам восприятия: теплота, уверенность, привлекательность'}
        </p>
      </div>

      <div className="flex flex-col tablet:flex-row gap-[var(--space-16)] tablet:gap-[var(--space-24)]">
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

        {/* Analysis panel */}
        <div className="flex-1 flex flex-col gap-[var(--space-16)]">
          {/* Description text */}
          <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] min-h-[40px]">
            {app.preAnalysis?.first_impression || (isSimplified ? DOC_DEFAULT_DESCRIPTION : DEFAULT_DESCRIPTION)}
          </p>

          {/* Analysis button — shown before any analysis starts */}
          {app.photo && !analysisRequested && !app.preAnalyzeLoading && !app.preAnalysis && (
            <button
              onClick={handleStartAnalysis}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium"
            >
              Запустить анализ
            </button>
          )}

          {/* Real loading state — API call in progress */}
          {app.preAnalyzeLoading && !app.preAnalysis && (
            <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-20)]">
              <div className="flex items-center gap-[var(--space-12)]">
                <div className="w-[18px] h-[18px] border-2 border-t-transparent rounded-full animate-spin shrink-0" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                <span className="text-[14px] leading-[20px] text-[#E6EEF8]">Анализ фото...</span>
              </div>
              <div className="flex items-center gap-[var(--space-12)] opacity-50">
                <div className="w-[18px] h-[18px] rounded-full border border-[rgba(255,255,255,0.1)]" />
                <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)]">Оценка параметров...</span>
              </div>
              <div className="flex items-center gap-[var(--space-12)] opacity-50">
                <div className="w-[18px] h-[18px] rounded-full border border-[rgba(255,255,255,0.1)]" />
                <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)]">Формирование результата...</span>
              </div>
              <div className="h-1.5 rounded-full glass-progress-track overflow-hidden mt-[var(--space-4)]">
                <div className="h-full rounded-full glass-progress-fill animate-pulse" style={{ width: '66%' }} />
              </div>
            </div>
          )}

          {/* Results — show when API resolved (success or error) */}
          {(app.preAnalysis || app.preAnalyzeError) && (
            <>
              <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                {displayParams ? displayParams.map((p) => (
                  <div key={p.key} className="flex flex-col gap-[var(--space-8)]">
                    <div className="flex items-center justify-between">
                      <span className="text-[14px] leading-[20px] text-[#E6EEF8]">{p.label}</span>
                      <span className="flex items-center gap-[var(--space-4)] text-[14px] leading-[20px] tabular-nums">
                        <span className="text-[var(--color-text-secondary)]">{p.value.toFixed(2)}</span>
                        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">/ 10</span>
                      </span>
                    </div>
                    <ProgressBar value={p.value} />
                  </div>
                )) : (
                  <div className="flex flex-col items-center gap-[var(--space-8)] text-center py-[var(--space-12)]">
                    {app.preAnalyzeError ? (
                      <>
                        <span className="text-[14px] text-[var(--color-text-muted)]">Не удалось загрузить анализ</span>
                        <button
                          onClick={() => { setAnalysisRequested(true); app.runPreAnalyze(); }}
                          className="glass-btn-ghost px-[var(--space-16)] py-[var(--space-6)] text-[13px] text-[#E6EEF8] rounded-[var(--radius-pill)]"
                        >
                          Повторить
                        </button>
                      </>
                    ) : (
                      <span className="text-[14px] text-[var(--color-text-muted)]">Загрузите фото для анализа</span>
                    )}
                  </div>
                )}
              </div>

              {/* Recommended styles (hidden for simplified document mode) */}
              {recommendation && !isSimplified && (
                <div className="flex flex-col gap-[var(--space-8)]">
                  <span className="text-[13px] leading-[18px] font-medium text-[var(--color-text-muted)]">Рекомендуемые стили</span>
                  {recommendation.styles.map((s) => (
                    <div
                      key={s.key}
                      onClick={() => { app.setSelectedStyleKey(s.key); onNext(); }}
                      className="gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[36px] cursor-pointer rounded-[var(--radius-12)] transition-all glass-row"
                      style={{ '--gb-color': 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.15)' } as React.CSSProperties}
                    >
                      <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">{s.icon}</div>
                      <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                        <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium truncate">{s.name}</span>
                        <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">{s.desc}</span>
                      </div>
                    </div>
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
              {isSimplified ? 'Выбрать формат' : 'Выбрать стиль'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
