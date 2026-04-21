import { WIZARD_STEPS, type WizardStepId, type WizardStep } from './shared';

interface Props {
  currentStep: WizardStepId;
  completedSteps: Set<WizardStepId>;
  onStepClick: (id: WizardStepId) => void;
  photoPreview?: string | null;
  analysisScore?: number | null;
  styleDelta?: number | null;
  finalScore?: number | null;
  steps?: readonly WizardStep[];
}

function getCircleContent(
  stepId: WizardStepId,
  isCompleted: boolean,
  isCurrent: boolean,
  stepNumber: number,
  props: Pick<Props, 'photoPreview' | 'analysisScore' | 'styleDelta' | 'finalScore'>,
  mobile: boolean,
) {
  if (isCompleted && !isCurrent) {
    if (stepId === 'upload' && props.photoPreview) {
      return <img src={props.photoPreview} alt="" className="w-full h-full rounded-full object-cover" />;
    }
    if (stepId === 'analysis' && props.analysisScore != null) {
      return <span className={`${mobile ? 'text-[9px]' : 'text-[11px]'} font-bold tabular-nums leading-none`}>{props.analysisScore.toFixed(1)}</span>;
    }
    if (stepId === 'style' && props.styleDelta != null && props.styleDelta > 0) {
      return <span className={`${mobile ? 'text-[8px]' : 'text-[10px]'} font-bold tabular-nums leading-none`}>+{props.styleDelta.toFixed(1)}</span>;
    }
    if (stepId === 'generate' && props.finalScore != null) {
      return <span className={`${mobile ? 'text-[9px]' : 'text-[11px]'} font-bold tabular-nums leading-none`}>{props.finalScore.toFixed(1)}</span>;
    }
    return mobile ? (
      <svg width="14" height="14" viewBox="0 0 18 18" fill="none">
        <path d="M5 9.5L7.5 12L13 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) : (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M5 9.5L7.5 12L13 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );
  }
  return stepNumber;
}

function getSegmentLabel(
  stepId: WizardStepId,
  isCompleted: boolean,
  props: Pick<Props, 'photoPreview' | 'analysisScore' | 'styleDelta' | 'finalScore'>,
): string | null {
  if (!isCompleted) return null;
  if (stepId === 'analysis' && props.analysisScore != null) return props.analysisScore.toFixed(1);
  if (stepId === 'style' && props.styleDelta != null && props.styleDelta > 0) return `+${props.styleDelta.toFixed(1)}`;
  if (stepId === 'generate' && props.finalScore != null) return props.finalScore.toFixed(1);
  return null;
}

export default function StepBar({ currentStep, completedSteps, onStepClick, photoPreview, analysisScore, styleDelta, finalScore, steps: customSteps }: Props) {
  const steps = customSteps ?? WIZARD_STEPS;
  const currentIdx = steps.findIndex(s => s.id === currentStep);
  const contextProps = { photoPreview, analysisScore, styleDelta, finalScore };

  return (
    <div className="w-full max-w-[960px] mx-auto">
      {/* Desktop / Tablet */}
      <div className="hidden tablet:flex items-center justify-between gap-[var(--space-24)]">
        {steps.map((step) => {
          const isCompleted = completedSteps.has(step.id);
          const isCurrent = step.id === currentStep;
          const stepIdx = steps.findIndex(s => s.id === step.id);
          const isClickable = isCompleted || stepIdx <= currentIdx;
          const showAvatar = isCompleted && !isCurrent && step.id === 'upload' && !!photoPreview;

          return (
            <button
              key={step.id}
              onClick={() => isClickable && onStepClick(step.id)}
              disabled={!isClickable}
              className={`relative z-[1] flex flex-col items-center gap-[var(--space-4)] transition-all ${
                isClickable ? 'cursor-pointer' : 'cursor-not-allowed'
              }`}
            >
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center font-semibold transition-all duration-300 ${
                  showAvatar ? 'overflow-hidden p-0' : 'text-[14px]'
                } ${
                  isCurrent
                    ? 'text-white shadow-lg'
                    : isCompleted
                      ? 'text-white'
                      : 'text-[var(--color-text-muted)] border border-[rgba(255,255,255,0.12)]'
                }`}
                style={
                  isCurrent
                    ? {
                        background: `rgb(var(--accent-r), var(--accent-g), var(--accent-b))`,
                        boxShadow: `0 0 20px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.4)`,
                      }
                    : isCompleted
                      ? { background: `rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.6)` }
                      : { background: 'rgba(255,255,255,0.04)' }
                }
              >
                {getCircleContent(step.id, isCompleted, isCurrent, step.number, contextProps, false)}
              </div>
              <div className="flex flex-col items-center gap-[2px]">
                <span className={`text-[12px] leading-[16px] font-medium transition-colors whitespace-nowrap ${
                  isCurrent ? 'text-[#E6EEF8]' : isCompleted ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-text-muted)]'
                }`}>
                  {step.title}
                </span>
                <span className={`text-[10px] leading-[14px] transition-colors whitespace-nowrap ${
                  isCurrent ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-text-muted)]'
                }`}>
                  {step.desc}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Mobile — segmented progress bar */}
      <div className="flex tablet:hidden flex-col gap-[var(--space-8)] px-[var(--space-4)]">
        <div className="flex items-center justify-between">
          <span className="text-[14px] leading-[20px] font-semibold text-[#E6EEF8]">
            {steps[currentIdx]?.title}
          </span>
          <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] tabular-nums">
            Шаг {currentIdx + 1} из {steps.length}
          </span>
        </div>

        <div className="flex items-start gap-[6px]">
          {steps.map((step, i) => {
            const isCompleted = completedSteps.has(step.id);
            const isCurrent = step.id === currentStep;
            const isClickable = isCompleted || i <= currentIdx;
            const label = getSegmentLabel(step.id, isCompleted, contextProps);
            const showThumb = isCompleted && step.id === 'upload' && !!photoPreview;

            return (
              <button
                key={step.id}
                onClick={() => isClickable && onStepClick(step.id)}
                disabled={!isClickable}
                className={`flex-1 flex flex-col items-center gap-[4px] ${isClickable ? 'cursor-pointer' : 'cursor-not-allowed'}`}
              >
                <div
                  className="w-full h-[6px] rounded-full transition-all duration-300"
                  style={
                    isCurrent
                      ? {
                          background: `rgb(var(--accent-r), var(--accent-g), var(--accent-b))`,
                          boxShadow: `0 0 8px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.5)`,
                        }
                      : isCompleted
                        ? { background: `rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.6)` }
                        : { background: 'rgba(255,255,255,0.08)' }
                  }
                />
                {showThumb ? (
                  <img src={photoPreview!} alt="" className="w-5 h-5 rounded-full object-cover" />
                ) : label ? (
                  <span className={`text-[10px] leading-[14px] tabular-nums font-medium ${
                    isCurrent ? 'text-[#E6EEF8]' : 'text-[var(--color-text-muted)]'
                  }`}>{label}</span>
                ) : (
                  <span className={`text-[10px] leading-[14px] tabular-nums ${
                    isCurrent ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-text-muted)]'
                  }`}>{step.number}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
