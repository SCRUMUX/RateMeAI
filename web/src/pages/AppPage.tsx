import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import NavBar from '../sections/NavBar';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import StepBar from '../components/wizard/StepBar';
import StepUpload from '../components/wizard/StepUpload';
import StepAnalysis from '../components/wizard/StepAnalysis';
import StepStyle from '../components/wizard/StepStyle';
import StepDocumentFormat from '../components/wizard/StepDocumentFormat';
import StepGenerate from '../components/wizard/StepGenerate';
import StorageModal from '../components/StorageModal';
import { useApp } from '../context/AppContext';
import { type WizardStepId, getWizardStepsForScenario } from '../components/wizard/shared';
import { getScenario } from '../scenarios/config';
import { restorePhotoAfterPayment, clearPersistedPaymentPhoto } from '../lib/photo-persist';

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
  const { scenarioSlug } = useParams<{ scenarioSlug: string }>();

  useEffect(() => {
    app.syncScenarioFromRoute(scenarioSlug);
  }, [scenarioSlug, app.syncScenarioFromRoute]);

  const wizardSteps = useMemo(
    () => getWizardStepsForScenario(app.scenarioStep3Mode),
    [app.scenarioStep3Mode],
  );
  const isDocumentScenario = app.scenarioStep3Mode === 'document_formats';

  const [returnedStep] = useState<WizardStepId | null>(() => {
    const saved = localStorage.getItem('returnToStep');
    if (saved && STEP_ORDER.includes(saved as WizardStepId)) {
      localStorage.removeItem('returnToStep');
      return saved as WizardStepId;
    }
    return null;
  });
  const [currentStep, setCurrentStep] = useState<WizardStepId>(returnedStep ?? 'upload');
  const [restoringPhoto, setRestoringPhoto] = useState(returnedStep != null && returnedStep !== 'upload');
  const [direction, setDirection] = useState(0);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [storageModalOpen, setStorageModalOpen] = useState(false);
  const visitedSteps = useRef(new Set<WizardStepId>(
    returnedStep
      ? STEP_ORDER.slice(0, STEP_ORDER.indexOf(returnedStep) + 1) as WizardStepId[]
      : ['upload'],
  ));
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!restoringPhoto) return;
    let cancelled = false;
    (async () => {
      try {
        const restored = await restorePhotoAfterPayment();
        if (cancelled) return;
        if (restored) {
          app.uploadPhoto(restored.file);
          if (restored.style) app.setSelectedStyleKey(restored.style);
          await clearPersistedPaymentPhoto();
        }
      } finally {
        if (!cancelled) setRestoringPhoto(false);
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const currentIdx = STEP_ORDER.indexOf(currentStep);

  const completedSteps = new Set<WizardStepId>();
  if (app.generatedImageUrl) {
    for (const step of STEP_ORDER) completedSteps.add(step);
  } else {
    for (const step of visitedSteps.current) {
      const stepIdx = STEP_ORDER.indexOf(step);
      if (stepIdx < currentIdx) completedSteps.add(step);
    }
  }

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
    if (restoringPhoto) return;
    if (!app.photo && currentStep !== 'upload') {
      setCurrentStep('upload');
      visitedSteps.current = new Set(['upload']);
    }
  }, [app.photo, currentStep, restoringPhoto]);

  async function handleImproveFromStorage(imageUrl: string) {
    try {
      const res = await fetch(imageUrl, { credentials: 'omit' });
      const blob = await res.blob();
      const file = new File([blob], 'improve.jpg', { type: blob.type || 'image/jpeg' });
      app.uploadPhoto(file);
      setStorageModalOpen(false);
      goToStep('upload');
    } catch {
      /* ignore fetch errors */
    }
  }

  const selectedStyle = app.effectiveStyleList.find(s => s.key === app.selectedStyleKey)
    ?? app.effectiveStyleList[0];
  const predictedDelta = selectedStyle
    ? (selectedStyle.deltaRange[0] + selectedStyle.deltaRange[1]) / 2
    : null;
  const beforeScore = app.preAnalysis?.score ?? null;
  const genAfterScore = app.afterScore;
  const displayAfterScore =
    (genAfterScore != null && beforeScore != null && genAfterScore >= beforeScore)
      ? genAfterScore
      : (genAfterScore != null && beforeScore == null)
        ? genAfterScore
        : beforeScore != null && predictedDelta != null
          ? +(beforeScore + predictedDelta).toFixed(2)
          : null;

  const showCounters = app.isAuthenticated;

  if (scenarioSlug && !getScenario(scenarioSlug)) {
    return <Navigate to="/app" replace />;
  }

  return (
    <div data-category={app.activeCategory} className="h-dvh flex flex-col w-full overflow-hidden selection:bg-brand-primary/30">
      <NavBar mode="app" onLoginClick={() => setAuthModalOpen(true)} />

      <main ref={scrollRef} className="relative flex-1 min-h-0 flex flex-col overflow-hidden">
        <MeshGradientBg />
        <EnergyField />

        <div className="relative z-[2] flex-1 min-h-0 flex flex-col items-center gap-[var(--space-16)] tablet:gap-[48px] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[var(--space-16)] tablet:py-[48px]">
          {/* Error toast */}
          {app.error && (
            <div className="glass-badge-danger fixed top-20 right-6 z-[200] max-w-[400px] p-[var(--space-16)] text-white rounded-[var(--radius-12)] text-[14px] leading-[20px] cursor-pointer"
              onClick={app.clearError}
            >
              {app.error}
            </div>
          )}

          {/* Step bar */}
          <div className="shrink-0">
            <StepBar
              currentStep={currentStep}
              completedSteps={completedSteps}
              onStepClick={handleStepClick}
              photoPreview={app.photo?.preview ?? null}
              analysisScore={beforeScore}
              styleDelta={predictedDelta}
              finalScore={displayAfterScore}
              steps={wizardSteps}
            />
          </div>

          {/* Balance & Storage counters */}
          {showCounters && (
            <div className="shrink-0 flex items-center justify-center gap-[var(--space-24)]">
              <div className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)]">
                <CoinIcon size={16} className="text-[var(--color-brand-primary)]" />
                <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">Баланс {app.balance}</span>
              </div>
              <button
                onClick={() => setStorageModalOpen(true)}
                className="glass-btn-ghost flex items-center gap-[var(--space-6)] px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-12)] cursor-pointer"
              >
                <ImageIcon size={16} className="text-[var(--color-brand-primary)]" />
                <span className="text-[14px] leading-[20px] font-medium text-[#E6EEF8]">Хранилище {app.taskHistoryCount}</span>
              </button>
            </div>
          )}

          {/* Step content with transitions */}
          <div className="flex-1 min-h-0 w-full max-w-[1200px]">
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={currentStep}
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
                className={`h-full ${currentStep === 'style' && !isDocumentScenario ? 'overflow-y-auto' : 'overflow-hidden'}`}
              >
                {currentStep === 'upload' && (
                  <StepUpload onNext={goNext} />
                )}
                {currentStep === 'analysis' && (
                  <StepAnalysis onNext={goNext} />
                )}
                {currentStep === 'style' && isDocumentScenario && (
                  <StepDocumentFormat onNext={goNext} />
                )}
                {currentStep === 'style' && !isDocumentScenario && (
                  <StepStyle onNext={goNext} />
                )}
                {currentStep === 'generate' && (
                  <StepGenerate onGoToStep={goToStep} onOpenStorage={() => setStorageModalOpen(true)} onRequestAuth={() => setAuthModalOpen(true)} />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>

      <StorageModal
        open={storageModalOpen}
        onClose={() => setStorageModalOpen(false)}
        items={app.taskHistory}
        onImprove={handleImproveFromStorage}
      />

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
