import { useState } from 'react';
import { useApp } from '../context/AppContext';
import DocumentPhotoLanding from './DocumentPhotoLanding';
import AppPage from './AppPage';

const SCENARIO_SLUG = 'document-photo';

export default function DocumentPhotoPage() {
  const app = useApp();
  const [showWizard, setShowWizard] = useState(false);

  if (!showWizard) {
    return <DocumentPhotoLanding onStart={() => setShowWizard(true)} />;
  }

  return (
    <AppPage
      scenarioSlugOverride={SCENARIO_SLUG}
      onBackToLanding={() => setShowWizard(false)}
    />
  );
}
