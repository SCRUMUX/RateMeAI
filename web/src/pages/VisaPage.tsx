import { useState, useCallback } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import VisaLanding from './VisaLanding';
import AppPage from './AppPage';
import { clearFlowStep, hasFlowStep, rememberFlowStep } from '../lib/flow-resume';
import { getVisaByCountry } from '../scenarios/visas';

/**
 * Wrapper that resolves ``/visa/:country`` to the right scenario,
 * then either renders ``VisaLanding`` (initial entry) or proxies to
 * ``AppPage`` once the user clicked "Сделать фото".
 *
 * Mirrors ``DocumentPhotoPage`` 1-to-1 — keeping the same shape means
 * the navigation/photo-persist behaviour is identical.
 */
export default function VisaPage() {
  const { country } = useParams<{ country: string }>();
  const visa = getVisaByCountry(country);
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

  if (!visa) {
    return <Navigate to="/" replace />;
  }

  if (!showWizard) {
    return (
      <VisaLanding
        visa={visa}
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
      scenarioSlugOverride={visa.slug}
      onBackToLanding={() => setShowWizard(false)}
    />
  );
}
