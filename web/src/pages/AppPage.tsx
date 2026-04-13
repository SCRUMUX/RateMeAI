import { useState, useCallback, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import NavBar from '../sections/NavBar';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import StepBar from '../components/wizard/StepBar';
import StepUpload from '../components/wizard/StepUpload';
import StepAnalysis from '../components/wizard/StepAnalysis';
import StepStyle from '../components/wizard/StepStyle';
import StepGenerate from '../components/wizard/StepGenerate';
import { useApp } from '../context/AppContext';
import { type WizardStepId } from '../components/wizard/shared';

const STEP_ORDER: WizardStepId[] = ['upload', 'analysis', 'style', 'generate'];

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 80 : -80,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -80 : 80,
    opacity: 0,
  }),
};

export default function AppPage() {
  const app = useApp();
  const [currentStep, setCurrentStep] = useState<WizardStepId>('upload');
  const [direction, setDirection] = useState(0);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const visitedSteps = useRef(new Set<WizardStepId>(['upload']));
  const scrollRef = useRef<HTMLDivElement>(null);

  const currentIdx = STEP_ORDER.indexOf(currentStep);

  const completedSteps = new Set<WizardStepId>();
  for (const step of visitedSteps.current) {
    const stepIdx = STEP_ORDER.indexOf(step);
    if (stepIdx < currentIdx) completedSteps.add(step);
  }
  if (app.generatedImageUrl) completedSteps.add('generate');

  const goToStep = useCallback((step: WizardStepId) => {
    const newIdx = STEP_ORDER.indexOf(step);
    setDirection(newIdx > currentIdx ? 1 : -1);
    setCurrentStep(step);
    visitedSteps.current.add(step);
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [currentIdx]);

  const handleStepClick = useCallback((step: WizardStepId) => {
    const stepIdx = STEP_ORDER.indexOf(step);
    if (stepIdx <= currentIdx || completedSteps.has(step)) {
      goToStep(step);
    }
  }, [currentIdx, completedSteps, goToStep]); // eslint-disable-line react-hooks/exhaustive-deps

  const goNext = useCallback(() => {
    if (currentIdx < STEP_ORDER.length - 1) {
      goToStep(STEP_ORDER[currentIdx + 1]);
    }
  }, [currentIdx, goToStep]);

  useEffect(() => {
    if (!app.photo && currentStep !== 'upload') {
      setCurrentStep('upload');
      visitedSteps.current = new Set(['upload']);
    }
  }, [app.photo, currentStep]);

  return (
    <div data-category={app.activeCategory} className="h-dvh flex flex-col w-full overflow-hidden selection:bg-brand-primary/30">
      <NavBar mode="app" onLoginClick={() => setAuthModalOpen(true)} />

      <main ref={scrollRef} className="relative flex-1 overflow-y-auto">
        <MeshGradientBg />
        <EnergyField />

        <div className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] tablet:gap-[var(--space-40)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[var(--space-24)] tablet:py-[var(--space-40)]">
          {/* Error toast */}
          {app.error && (
            <div className="glass-badge-danger fixed top-20 right-6 z-[200] max-w-[400px] p-[var(--space-16)] text-white rounded-[var(--radius-12)] text-[14px] leading-[20px] cursor-pointer"
              onClick={app.clearError}
            >
              {app.error}
            </div>
          )}

          {/* Step bar */}
          <StepBar
            currentStep={currentStep}
            completedSteps={completedSteps}
            onStepClick={handleStepClick}
          />

          {/* Step content with transitions */}
          <div className="w-full max-w-[1200px]">
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={currentStep}
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
              >
                {currentStep === 'upload' && (
                  <StepUpload onNext={goNext} />
                )}
                {currentStep === 'analysis' && (
                  <StepAnalysis onNext={goNext} />
                )}
                {currentStep === 'style' && (
                  <StepStyle onNext={goNext} />
                )}
                {currentStep === 'generate' && (
                  <StepGenerate onGoToStep={goToStep} />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>

      <AuthModal
        open={authModalOpen || !app.isAuthenticated}
        onClose={() => setAuthModalOpen(false)}
        required={!app.isAuthenticated}
        onOAuth={async (provider) => {
          await app.loginWithOAuth(provider);
        }}
      />
    </div>
  );
}
