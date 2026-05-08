import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { POLICIES } from '../data/policies';
import useDocumentMeta from '../lib/useDocumentMeta';

/**
 * Privacy policy page — thin wrapper around the shared PrivacyBody from
 * `web/src/data/policies.tsx`. Same content is rendered inside PolicyModal
 * to keep a single source of truth.
 *
 * Route: /privacy.
 * Legal frameworks: 152-ФЗ (RU), GDPR (EU), CCPA/CPRA (US).
 */
export default function PrivacyPolicy() {
  const entry = POLICIES.privacy;
  const { t } = useTranslation(['common', 'seo', 'policies']);

  useDocumentMeta({
    title: t('seo:privacy.title', { defaultValue: `${entry.shortTitle} · Look Studio` }),
    description: t('seo:privacy.description'),
    canonicalPath: '/privacy',
  });

  const backLabel = t('common:actions.backToHome');
  const versionLabel = t('policies:versionPrefix', {
    version: '1.0',
    date: entry.lastUpdated,
  });

  return (
    <div className="min-h-screen w-full bg-[var(--color-bg-base)] text-[var(--color-text-primary)]">
      <div className="max-w-[860px] mx-auto px-6 py-12">
        <div className="mb-8">
          <Link
            to="/"
            className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            {backLabel}
          </Link>
        </div>

        <h1 className="text-[32px] font-bold mb-2">{entry.title}</h1>
        <p className="text-[13px] text-[var(--color-text-muted)] mb-10">
          {versionLabel}
        </p>

        <article className="prose prose-invert max-w-none space-y-6 text-[15px] leading-[1.7]">
          {entry.body}
        </article>

        <div className="mt-16 pt-8 border-t border-white/10 text-center">
          <Link
            to="/"
            className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            {backLabel}
          </Link>
        </div>
      </div>
    </div>
  );
}
