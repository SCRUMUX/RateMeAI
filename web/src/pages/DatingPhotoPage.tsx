import { useCallback, useState } from 'react';
import { useApp } from '../context/AppContext';
import DatingPhotoLanding from './DatingPhotoLanding';
import AppPage from './AppPage';
import { clearFlowStep, hasFlowStep, rememberFlowStep } from '../lib/flow-resume';

const SCENARIO_SLUG = 'dating-photo';

export default function DatingPhotoPage() {
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
      <DatingPhotoLanding
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

