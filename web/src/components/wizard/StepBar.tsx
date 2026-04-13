import { WIZARD_STEPS, type WizardStepId } from './shared';

interface Props {
  currentStep: WizardStepId;
  completedSteps: Set<WizardStepId>;
  onStepClick: (id: WizardStepId) => void;
}

export default function StepBar({ currentStep, completedSteps, onStepClick }: Props) {
  const currentIdx = WIZARD_STEPS.findIndex(s => s.id === currentStep);

  return (
    <div className="w-full max-w-[800px] mx-auto">
      {/* Desktop / Tablet */}
      <div className="hidden tablet:flex items-center justify-between relative">
        {/* Connector line */}
        <div className="absolute top-5 left-[60px] right-[60px] h-[2px] bg-[rgba(255,255,255,0.08)]" />
        <div
          className="absolute top-5 left-[60px] h-[2px] transition-all duration-500 ease-out"
          style={{
            width: `${currentIdx > 0 ? (currentIdx / (WIZARD_STEPS.length - 1)) * 100 : 0}%`,
            maxWidth: 'calc(100% - 120px)',
            background: 'rgb(var(--accent-r), var(--accent-g), var(--accent-b))',
          }}
        />

        {WIZARD_STEPS.map((step) => {
          const isCompleted = completedSteps.has(step.id);
          const isCurrent = step.id === currentStep;
          const stepIdx = WIZARD_STEPS.findIndex(s => s.id === step.id);
          const isClickable = isCompleted || stepIdx <= currentIdx;

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
                className={`w-10 h-10 rounded-full flex items-center justify-center text-[14px] font-semibold transition-all duration-300 ${
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
                {isCompleted && !isCurrent ? (
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M5 9.5L7.5 12L13 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ) : (
                  step.number
                )}
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

            return (
              <button
                key={step.id}
                onClick={() => isClickable && onStepClick(step.id)}
                disabled={!isClickable}
                className={`w-8 h-8 rounded-full flex items-center justify-center text-[12px] font-semibold transition-all ${
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
                {isCompleted && !isCurrent ? (
                  <svg width="14" height="14" viewBox="0 0 18 18" fill="none">
                    <path d="M5 9.5L7.5 12L13 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ) : (
                  step.number
                )}
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
