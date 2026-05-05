import { Link } from 'react-router-dom';
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

  useDocumentMeta({
    title: `${entry.shortTitle} · Look Studio`,
    description:
      'Политика обработки персональных данных Look Studio: как мы собираем, храним и защищаем данные пользователей в соответствии с 152-ФЗ и GDPR.',
    canonicalPath: '/privacy',
  });

  return (
    <div className="min-h-screen w-full bg-[var(--color-bg-base)] text-[var(--color-text-primary)]">
      <div className="max-w-[860px] mx-auto px-6 py-12">
        <div className="mb-8">
          <Link
            to="/"
            className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            ← На главную
          </Link>
        </div>

        <h1 className="text-[32px] font-bold mb-2">{entry.title}</h1>
        <p className="text-[13px] text-[var(--color-text-muted)] mb-10">
          Версия 1.0 · Последнее обновление: {entry.lastUpdated}
        </p>

        <article className="prose prose-invert max-w-none space-y-6 text-[15px] leading-[1.7]">
          {entry.body}
        </article>

        <div className="mt-16 pt-8 border-t border-white/10 text-center">
          <Link
            to="/"
            className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            ← На главную
          </Link>
        </div>
      </div>
    </div>
  );
}
