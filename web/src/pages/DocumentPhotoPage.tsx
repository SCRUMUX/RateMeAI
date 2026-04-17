import { useState, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import DocumentPhotoLanding from './DocumentPhotoLanding';
import AppPage from './AppPage';
import { clearFlowStep, hasFlowStep, rememberFlowStep } from '../lib/flow-resume';

const SCENARIO_SLUG = 'document-photo';

export default function DocumentPhotoPage() {
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
      <DocumentPhotoLanding
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
