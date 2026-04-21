import { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import CategoryTabs from '../CategoryTabs';
import { PARAM_LABELS } from './shared';
import { COMING_SOON_CATEGORIES, type CategoryId } from '../../data/styles';

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

  const directionLocked = COMING_SOON_CATEGORIES.includes(activeTab);
  const canContinue = hasRealScores && !directionLocked;

  function handleDirectionChange(id: CategoryId) {
    app.setActiveCategory(id);
    app.setSelectedStyleKey('');
  }

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
    <div className="flex flex-col gap-[var(--space-8)] tablet:gap-[var(--space-12)] w-full max-w-[800px] mx-auto tablet:h-full">
      <div className="flex flex-col items-center gap-[var(--space-4)] text-center shrink-0">
        <h2 className="text-[20px] tablet:text-[24px] leading-[1.2] font-semibold text-[#E6EEF8]">
          {isSimplified ? 'Анализ фото' : 'Анализ восприятия'}
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          {isSimplified
            ? 'Проверим фото под требования документов: кадр, ракурс, фон и освещение'
            : 'Покажем, как ваше фото считывается с первого взгляда: теплота, уверенность, привлекательность'}
        </p>
      </div>

      <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] tablet:gap-[var(--space-24)] tablet:flex-1 tablet:min-h-0">
        {/* Photo card with score */}
        <div className="gradient-border-card glass-card flex flex-col w-full tablet:w-[260px] shrink-0 rounded-[var(--radius-12)] overflow-hidden">
          <div className="w-full aspect-[3/4] tablet:h-[320px] shrink-0 bg-[rgba(255,255,255,0.02)] overflow-hidden">
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
        <div className="flex-1 flex flex-col gap-[var(--space-12)] min-h-0">
          {/* Description text */}
          <p className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-secondary)] min-h-[36px]">
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
            <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-12)] rounded-[var(--radius-12)] p-[var(--space-16)]">
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

          {/* Results — parameters + direction picker, then soft warnings below */}
          {(app.preAnalysis || app.preAnalyzeError) && (
            <>
              <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-10)] rounded-[var(--radius-12)] p-[var(--space-12)]">
                {displayParams ? displayParams.map((p) => (
                  <div key={p.key} className="flex flex-col gap-[var(--space-6)]">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[#E6EEF8]">{p.label}</span>
                      <span className="flex items-center gap-[var(--space-4)] text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] tabular-nums">
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

              {/* Direction picker — обычный сценарий */}
              {hasRealScores && !isSimplified && (
                <div className="flex flex-col gap-[var(--space-8)]">
                  <span className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] font-medium text-[#E6EEF8]">Для чего улучшаем фото?</span>
                  {!app.scenarioHideCategoryTabs && (
                    <CategoryTabs active={activeTab} onChange={handleDirectionChange} />
                  )}
                </div>
              )}

              {/* Soft warnings — compact, below results */}
              {app.preAnalysis?.input_quality?.soft_warnings?.length ? (
                <div
                  className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-10)]"
                  style={{ '--gb-color': 'rgba(255, 190, 120, 0.35)' } as React.CSSProperties}
                >
                  <div className="flex items-start gap-[var(--space-8)]">
                    <svg
                      width="16" height="16" viewBox="0 0 24 24" fill="none"
                      className="shrink-0 mt-[2px]" aria-hidden="true"
                    >
                      <path d="M12 3L2 21h20L12 3z" stroke="#FFC27A" strokeWidth="1.6" strokeLinejoin="round" />
                      <path d="M12 10v5" stroke="#FFC27A" strokeWidth="1.6" strokeLinecap="round" />
                      <circle cx="12" cy="18" r="0.9" fill="#FFC27A" />
                    </svg>
                    <div className="flex flex-col gap-[var(--space-4)]">
                      <span className="text-[12px] leading-[16px] font-medium text-[#FFD6A8]">
                        Качество фото может повлиять на результат
                      </span>
                      <ul className="flex flex-col gap-[var(--space-2)]">
                        {app.preAnalysis!.input_quality!.soft_warnings.map((w) => (
                          <li
                            key={w.code}
                            className="text-[11px] leading-[15px] text-[var(--color-text-secondary)]"
                          >
                            <span className="text-[#E6EEF8]">{w.message}</span>{' '}
                            <span className="text-[var(--color-text-muted)]">{w.suggestion}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : null}
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

          {/* Next button — pinned to bottom of right column on desktop */}
          {hasRealScores && isSimplified && (
            <button
              onClick={onNext}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium tablet:mt-auto"
            >
              Выбрать формат
            </button>
          )}
          {hasRealScores && !isSimplified && (
            <button
              onClick={onNext}
              disabled={!canContinue}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium tablet:mt-auto disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {directionLocked ? 'Направление скоро' : 'Продолжить'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
