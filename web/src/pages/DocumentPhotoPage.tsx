import { useApp } from '../context/AppContext';
import DocumentPhotoLanding from './DocumentPhotoLanding';
import AppPage from './AppPage';

const SCENARIO_SLUG = 'document-photo';

export default function DocumentPhotoPage() {
  const { hasRealAuth } = useApp();

  if (!hasRealAuth) {
    return <DocumentPhotoLanding />;
  }

  return <AppPage scenarioSlugOverride={SCENARIO_SLUG} />;
}
