import { useState, useCallback, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import NavBar from '../sections/NavBar';
import Footer from '../sections/Footer';
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

  const currentIdx = STEP_ORDER.indexOf(currentStep);

  const completedSteps = new Set<WizardStepId>();
  if (app.photo) completedSteps.add('upload');
  if (app.preAnalysis || (!app.isAuthenticated && app.simulationDone)) completedSteps.add('analysis');
  if (app.selectedStyleKey) completedSteps.add('style');
  if (app.generatedImageUrl) completedSteps.add('generate');

  const goToStep = useCallback((step: WizardStepId) => {
    const newIdx = STEP_ORDER.indexOf(step);
    setDirection(newIdx > currentIdx ? 1 : -1);
    setCurrentStep(step);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [currentIdx]);

  const handleStepClick = useCallback((step: WizardStepId) => {
    const stepIdx = STEP_ORDER.indexOf(step);
    if (stepIdx <= currentIdx || completedSteps.has(step)) {
      goToStep(step);
    }
  }, [currentIdx, completedSteps, goToStep]);

  const goNext = useCallback(() => {
    if (currentIdx < STEP_ORDER.length - 1) {
      goToStep(STEP_ORDER[currentIdx + 1]);
    }
  }, [currentIdx, goToStep]);

  // If photo is removed, go back to upload
  useEffect(() => {
    if (!app.photo && currentStep !== 'upload') {
      goToStep('upload');
    }
  }, [app.photo]);

  return (
    <div data-category={app.activeCategory} className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} />
      <main className="relative pt-[68px] tablet:pt-[76px]">
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
          <div className="w-full max-w-[1200px] min-h-[60vh]">
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
                  <StepAnalysis
                    onNext={goNext}
                    onOpenAuthModal={() => setAuthModalOpen(true)}
                  />
                )}
                {currentStep === 'style' && (
                  <StepStyle onNext={goNext} />
                )}
                {currentStep === 'generate' && (
                  <StepGenerate
                    onOpenAuthModal={() => setAuthModalOpen(true)}
                    onGoToStep={goToStep}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>
      <Footer />

      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onOAuth={async (provider) => {
          await app.loginWithOAuth(provider);
        }}
      />
    </div>
  );
}
