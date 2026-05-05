import { useCallback, useState } from 'react';
import { useApp } from '../context/AppContext';
import ResumePhotoLanding from './ResumePhotoLanding';
import AppPage from './AppPage';
import { clearFlowStep, hasFlowStep, rememberFlowStep } from '../lib/flow-resume';

const SCENARIO_SLUG = 'resume-photo';

export default function ResumePhotoPage() {
  const app = useApp();
  const [showWizard, setShowWizard] = useState(hasFlowStep);
  const [pendingStart, setPendingStart] = useState(false);
  const hasScenarioAccess = app.canAccessApp;

  const handleStart = useCallback(() => {
    if (hasScenarioAccess) {
      setShowWizard(true);
    } else {
      rememberFlowStep('upload');
      setPendingStart(true);
    }
  }, [hasScenarioAccess]);

  if (!showWizard) {
    return (
      <ResumePhotoLanding
        onStart={handleStart}
        showAuth={pendingStart}
        onAuthClose={() => {
          clearFlowStep('upload');
          setPendingStart(false);
        }}
      />
    );
  }

  return (
    <AppPage
      scenarioSlugOverride={SCENARIO_SLUG}
      onBackToLanding={() => setShowWizard(false)}
    />
  );
}

