import { WIZARD_STEPS, type WizardStepId } from './shared';

interface Props {
  currentStep: WizardStepId;
  completedSteps: Set<WizardStepId>;
  onStepClick: (id: WizardStepId) => void;
  photoPreview?: string | null;
  analysisScore?: number | null;
  styleDelta?: number | null;
  finalScore?: number | null;
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

export default function StepBar({ currentStep, completedSteps, onStepClick, photoPreview, analysisScore, styleDelta, finalScore }: Props) {
  const currentIdx = WIZARD_STEPS.findIndex(s => s.id === currentStep);
  const contextProps = { photoPreview, analysisScore, styleDelta, finalScore };

  return (
    <div className="w-full max-w-[800px] mx-auto">
      {/* Desktop / Tablet */}
      <div className="hidden tablet:flex items-center justify-between">
        {WIZARD_STEPS.map((step) => {
          const isCompleted = completedSteps.has(step.id);
          const isCurrent = step.id === currentStep;
          const stepIdx = WIZARD_STEPS.findIndex(s => s.id === step.id);
          const isClickable = isCompleted || stepIdx <= currentIdx;
          const showAvatar = isCompleted && !isCurrent && step.id === 'upload' && !!photoPreview;

          return (
            <button
              key={step.id}
              onClick={() => isClickable && onStepClick(step.id)}
              disabled={!isClickable}
              className={`relative z-[1] flex flex-col items-center gap-[var(--space-8)] transition-all ${
                isClickable ? 'cursor-pointer' : 'cursor-not-allowed'
              }`}
            >
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold transition-all duration-300 ${
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
                <span className={`text-[13px] leading-[18px] font-medium transition-colors ${
                  isCurrent ? 'text-[#E6EEF8]' : isCompleted ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-text-muted)]'
                }`}>
                  {step.title}
                </span>
                <span className={`text-[11px] leading-[14px] transition-colors ${
                  isCurrent ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-text-muted)]'
                }`}>
                  {step.desc}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Mobile */}
      <div className="flex tablet:hidden items-center gap-[var(--space-12)] px-[var(--space-4)]">
        <div className="flex items-center gap-[var(--space-6)]">
          {WIZARD_STEPS.map((step) => {
            const isCompleted = completedSteps.has(step.id);
            const isCurrent = step.id === currentStep;
            const stepIdx = WIZARD_STEPS.findIndex(s => s.id === step.id);
            const isClickable = isCompleted || stepIdx <= currentIdx;
            const showAvatar = isCompleted && !isCurrent && step.id === 'upload' && !!photoPreview;

            return (
              <button
                key={step.id}
                onClick={() => isClickable && onStepClick(step.id)}
                disabled={!isClickable}
                className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold transition-all ${
                  showAvatar ? 'overflow-hidden p-0' : 'text-[12px]'
                } ${
                  isClickable ? 'cursor-pointer' : 'cursor-not-allowed'
                } ${
                  isCurrent
                    ? 'text-white'
                    : isCompleted
                      ? 'text-white'
                      : 'text-[var(--color-text-muted)] border border-[rgba(255,255,255,0.12)]'
                }`}
                style={
                  isCurrent
                    ? {
                        background: `rgb(var(--accent-r), var(--accent-g), var(--accent-b))`,
                        boxShadow: `0 0 12px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.4)`,
                      }
                    : isCompleted
                      ? { background: `rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.6)` }
                      : { background: 'rgba(255,255,255,0.04)' }
                }
              >
                {getCircleContent(step.id, isCompleted, isCurrent, step.number, contextProps, true)}
              </button>
            );
          })}
        </div>
        <div className="flex flex-col gap-[1px] min-w-0">
          <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">
            {WIZARD_STEPS[currentIdx].title}
          </span>
          <span className="text-[12px] leading-[16px] text-[var(--color-text-secondary)]">
            {WIZARD_STEPS[currentIdx].desc}
          </span>
        </div>
      </div>
    </div>
  );
}
