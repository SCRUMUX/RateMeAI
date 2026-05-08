import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useApp } from '../../context/AppContext';
import ProgressBar from './ProgressBar';
import CategoryTabs from '../CategoryTabs';
import { COMING_SOON_CATEGORIES, type CategoryId } from '../../data/styles';
import { sanitizeLLMText } from '../../lib/sanitize';
import { PlaceholderUpload } from '../effects/PlaceholderArt';
import { isApprovalProbabilityScenario } from '../../scenarios/config';

interface Props {
  onNext: () => void;
}

export default function StepAnalysis({ onNext }: Props) {
  const app = useApp();
  const { t } = useTranslation('wizard');
  const [analysisRequested, setAnalysisRequested] = useState(false);
  const isSimplified = app.scenarioSimplifiedAnalysis;

  const activeTab = app.activeCategory;

  const hasRealScores = !!app.preAnalysis;
  const beforeScore = hasRealScores ? app.preAnalysis!.score : null;
  const isApproval = isApprovalProbabilityScenario(app.scenarioSlug);
  const approvalProbability =
    isApproval && app.preAnalysis?.approval_probability != null
      ? app.preAnalysis.approval_probability
      : null;
  const visaCompliance = app.preAnalysis?.visa_compliance ?? app.complianceChecklist ?? null;
  const isVisa = app.scenarioSlug?.startsWith('visa-') ?? false;

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
    <div className="flex flex-col gap-[var(--space-12)] w-full max-w-[800px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-4)] text-center">
        <h2 className="text-[20px] tablet:text-[28px] leading-[1.2] font-semibold text-[var(--color-text-primary)]">
          {isApproval
            ? (isVisa ? t('analysis.titleVisa') : t('analysis.titleDocument'))
            : isSimplified ? t('analysis.titleSimplified') : t('analysis.title')}
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          {isApproval
            ? (isVisa ? t('analysis.subtitleVisa') : t('analysis.subtitleDocument'))
            : isSimplified ? t('analysis.subtitleSimplified') : t('analysis.subtitle')}
        </p>
      </div>

      <div className="flex flex-col items-center gap-[var(--space-16)] w-full">
        {/* Photo card with overall score — single centered column */}
        <div className="gradient-border-card glass-card flex flex-col w-full max-w-[260px] shrink-0 rounded-[var(--radius-12)] overflow-hidden">
          <div className="w-full aspect-[4/5] shrink-0 bg-[var(--glass-surface-soft)] overflow-hidden">
            {app.photo ? (
              <img src={app.photo.preview} alt={t('analysis.altOriginal')} className="w-full h-full object-cover" />
            ) : (
              <PlaceholderUpload className="w-full h-full opacity-50 text-[var(--color-text-secondary)]" />
            )}
          </div>
          <div className="flex flex-col gap-[var(--space-8)] p-[var(--space-12)]">
            <div className="flex items-center justify-between">
              <span className="text-[16px] leading-[24px] text-[var(--color-text-primary)] font-medium">
                {isApproval ? t('analysis.approvalProbability') : t('analysis.originalLabel')}
              </span>
              {isApproval && approvalProbability != null ? (
                <span className="flex items-baseline gap-1">
                  <span className="text-[15px] leading-[22px] text-[var(--color-text-primary)] font-semibold">
                    {approvalProbability.toFixed(1)}
                  </span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">%</span>
                </span>
              ) : beforeScore != null ? (
                <span className="flex items-center gap-1">
                  <span className="text-[14px] leading-[20px] text-[var(--color-text-secondary)]">{beforeScore.toFixed(2)}</span>
                  <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)]">{t('analysis.scoreOf')}</span>
                </span>
              ) : null}
            </div>
            {isApproval && approvalProbability != null ? (
              <ProgressBar value={approvalProbability} max={100} />
            ) : beforeScore != null ? (
              <ProgressBar value={beforeScore} />
            ) : null}
          </div>
        </div>

        {/* Analysis panel — moved under the photo, centered, comfortable max-width */}
        <div className="flex flex-col gap-[var(--space-16)] w-full max-w-[520px]">
          {/* Description text (plain prose — any stray HTML/markdown from the LLM is stripped) */}
          <p className="text-[14px] leading-[20px] text-[var(--color-text-secondary)] min-h-[40px] whitespace-pre-wrap text-center">
            {sanitizeLLMText(app.preAnalysis?.first_impression, 600) || (isSimplified ? t('analysis.defaultDescriptionDoc') : t('analysis.defaultDescription'))}
          </p>

          {/* Analysis button — shown before any analysis starts */}
          {app.photo && !analysisRequested && !app.preAnalyzeLoading && !app.preAnalysis && (
            <button
              onClick={handleStartAnalysis}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium"
            >
              {t('analysis.startButton')}
            </button>
          )}

          {/* Real loading state — API call in progress */}
          {app.preAnalyzeLoading && !app.preAnalysis && (
            <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-16)] rounded-[var(--radius-12)] p-[var(--space-20)]">
              <div className="flex items-center gap-[var(--space-12)]">
                <div className="w-[18px] h-[18px] border-2 border-t-transparent rounded-full animate-spin shrink-0" style={{ borderColor: 'rgba(var(--accent-r),var(--accent-g),var(--accent-b),0.5)', borderTopColor: 'transparent' }} />
                <span className="text-[14px] leading-[20px] text-[var(--color-text-primary)]">{t('analysis.loading')}</span>
              </div>
              <div className="flex items-center gap-[var(--space-12)] opacity-50">
                <div className="w-[18px] h-[18px] rounded-full border border-[var(--glass-border)]" />
                <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)]">{t('analysis.loadingParams')}</span>
              </div>
              <div className="flex items-center gap-[var(--space-12)] opacity-50">
                <div className="w-[18px] h-[18px] rounded-full border border-[var(--glass-border)]" />
                <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)]">{t('analysis.loadingResult')}</span>
              </div>
              <div className="h-1.5 rounded-full glass-progress-track overflow-hidden mt-[var(--space-4)]">
                <div className="h-full rounded-full glass-progress-fill animate-pulse" style={{ width: '66%' }} />
              </div>
            </div>
          )}

          {/* Visa/document compliance checklist — shown for approval-probability scenarios. */}
          {isApproval && hasRealScores && visaCompliance && visaCompliance.length > 0 && (
            <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-16)]">
              <p className="text-[13px] leading-[18px] font-medium text-[var(--color-text-primary)] mb-[var(--space-10)]">
                {t('analysis.checklistTitle')}
              </p>
              <ul className="flex flex-col gap-[var(--space-6)]">
                {visaCompliance.map((item) => {
                  const status = item.status || 'pending';
                  const colorClass =
                    status === 'passed'
                      ? 'text-[var(--color-success-base, #4ade80)]'
                      : status === 'failed'
                        ? 'text-[var(--color-danger)]'
                        : status === 'warn'
                          ? 'text-[var(--color-warning-base)]'
                          : 'text-[var(--color-text-muted)]';
                  return (
                    <li
                      key={item.rule}
                      className="flex items-start gap-[var(--space-8)] text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)]"
                    >
                      <span className={`shrink-0 mt-[2px] ${colorClass}`}>•</span>
                      <span>{item.rule}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Soft warnings from pre-flight quality gate — shown BEFORE any paid call */}
          {app.preAnalysis?.input_quality?.soft_warnings?.length ? (
            <div
              className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-12)]"
              style={{ '--gb-color': 'color-mix(in srgb, var(--color-warning-base) 35%, transparent)' } as React.CSSProperties}
            >
              <div className="flex items-start gap-[var(--space-10)]">
                <svg
                  width="18" height="18" viewBox="0 0 24 24" fill="none"
                  className="shrink-0 mt-[2px] text-[var(--color-warning-base)]" aria-hidden="true"
                >
                  <path d="M12 3L2 21h20L12 3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                  <path d="M12 10v5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  <circle cx="12" cy="18" r="0.9" fill="currentColor" />
                </svg>
                <div className="flex flex-col gap-[var(--space-6)]">
                  <span className="text-[13px] leading-[18px] font-medium text-[var(--color-warning-base)]">
                    {t('analysis.softWarningsTitle')}
                  </span>
                  <ul className="flex flex-col gap-[var(--space-4)]">
                    {app.preAnalysis!.input_quality!.soft_warnings.map((w) => (
                      <li
                        key={w.code}
                        className="text-[12px] leading-[16px] text-[var(--color-text-secondary)]"
                      >
                        <span className="text-[var(--color-text-primary)]">{w.message}</span>{' '}
                        <span className="text-[var(--color-text-muted)]">{w.suggestion}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : null}

          {/* Inline error fallback — компактная замена детальной панели,
              когда API не смог отдать ни общий, ни детальный скор. */}
          {!hasRealScores && app.preAnalyzeError && (
            <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
              <span className="text-[13px] text-[var(--color-text-muted)]">{t('analysis.loadFailed')}</span>
              <button
                onClick={() => { setAnalysisRequested(true); app.runPreAnalyze(); }}
                className="glass-btn-ghost px-[var(--space-16)] py-[var(--space-6)] text-[13px] text-[var(--color-text-primary)] rounded-[var(--radius-pill)]"
              >
                {t('analysis.retry')}
              </button>
            </div>
          )}

          {/* Direction picker — обычный сценарий */}
          {hasRealScores && !isSimplified && (
            <div className="flex flex-col gap-[var(--space-10)]">
              <span className="text-[14px] leading-[20px] font-medium text-[var(--color-text-primary)] text-center">{t('analysis.directionPrompt')}</span>
              {!app.scenarioHideCategoryTabs && (
                <CategoryTabs active={activeTab} onChange={handleDirectionChange} />
              )}
            </div>
          )}

          {/* No photo */}
          {!app.photo && (
            <div className="text-[14px] text-[var(--color-text-muted)] text-center">
              {t('analysis.noPhoto')}
            </div>
          )}

          {/* Next button */}
          {hasRealScores && isSimplified && (
            <button
              onClick={onNext}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)]"
            >
              {t('analysis.selectFormat')}
            </button>
          )}
          {hasRealScores && !isSimplified && (
            <button
              onClick={onNext}
              disabled={!canContinue}
              className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {directionLocked ? t('analysis.directionLocked') : t('analysis.continue')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
