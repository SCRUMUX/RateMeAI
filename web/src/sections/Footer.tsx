import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { AicaIcon } from '@ai-ds/core/icons';
import { useTranslation } from 'react-i18next';
import LogoEmblem from '../assets/LogoEmblem';
import {
  findBlock,
  useLandingHome,
  coalesceCmsString,
  type FooterItem,
  type FooterSocialItem,
  type LandingPage,
} from '../lib/landing-cms';
import { listScenariosForFooter } from '../scenarios/config';
import { useLandingModals } from '../context/LandingModalsContext';

interface FooterProps {
  cmsPage?: LandingPage | null;
}

interface ProductItem {
  label: string;
  href: string;
  external?: boolean;
}

interface FooterCmsData {
  brand?: { title?: unknown; tagline?: unknown };
  products?: unknown;
  support?: unknown;
  documents?: unknown;
  social?: unknown;
  links?: unknown;
  creditsText?: unknown;
  creditsLinkLabel?: unknown;
  creditsLinkHref?: unknown;
  copyright?: unknown;
}

function asNormString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function asProducts(value: unknown): ProductItem[] | null {
  if (!Array.isArray(value)) return null;
  const out: ProductItem[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const obj = item as Record<string, unknown>;
    const label = asNormString(obj.label).trim();
    const href = asNormString(obj.href).trim();
    if (!label || !href) continue;
    out.push({ label, href, external: Boolean(obj.external) });
  }
  return out.length ? out : null;
}

function asFooterItems(value: unknown): FooterItem[] {
  if (!Array.isArray(value)) return [];
  const out: FooterItem[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') continue;
    const obj = raw as Record<string, unknown>;
    const label = asNormString(obj.label).trim();
    if (!label) continue;
    const action = coalesceCmsString(obj.action, 'link');
    if (action === 'policy') {
      const policyId = asNormString(obj.policyId).trim();
      if (!policyId) continue;
      out.push({ label, action: 'policy', policyId });
    } else if (action === 'support') {
      out.push({ label, action: 'support' });
    } else {
      const href = asNormString(obj.href).trim();
      if (!href) continue;
      out.push({ label, action: 'link', href, external: Boolean(obj.external) });
    }
  }
  return out;
}

function asSocialItems(value: unknown): FooterSocialItem[] {
  if (!Array.isArray(value)) return [];
  const out: FooterSocialItem[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') continue;
    const obj = raw as Record<string, unknown>;
    const label = asNormString(obj.label).trim();
    const href = asNormString(obj.href).trim();
    if (!label || !href) continue;
    out.push({
      label,
      href,
      icon: coalesceCmsString(obj.icon, 'telegram'),
    });
  }
  return out;
}

function buildDefaultDocuments(t: (key: string) => string): FooterItem[] {
  return [
    { label: t('footer.documents.privacy'), action: 'policy', policyId: 'privacy' },
    { label: t('footer.documents.terms'), action: 'policy', policyId: 'terms' },
    { label: t('footer.documents.consents'), action: 'policy', policyId: 'consents' },
    { label: t('footer.documents.cookie'), action: 'policy', policyId: 'cookie' },
    { label: t('footer.documents.refund'), action: 'policy', policyId: 'refund' },
  ];
}

function buildDefaultSupport(t: (key: string) => string): FooterItem[] {
  return [
    { label: t('footer.support.contact'), action: 'support' },
    { label: t('footer.support.faq'), action: 'support' },
  ];
}

function buildDefaultSocial(t: (key: string) => string): FooterSocialItem[] {
  return [
    { label: t('footer.social.ux4ai'), href: 'https://t.me/ux4ai', icon: 'telegram' },
  ];
}

function TelegramIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M21.94 4.42c.34-1.61-.6-2.27-1.71-1.86L2.71 9.4c-1.18.46-1.16 1.12-.2 1.42l4.5 1.4 10.43-6.59c.49-.32.94-.15.57.18l-8.45 7.62-.32 4.6c.46 0 .67-.21.91-.45l2.18-2.12 4.55 3.36c.83.46 1.43.22 1.65-.77l2.99-14.04z" />
    </svg>
  );
}

function ColumnHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[12px] tablet:text-[13px] uppercase tracking-[0.08em] text-[var(--color-text-muted)] font-medium mb-[var(--space-12)]">
      {children}
    </h3>
  );
}

export default function Footer({ cmsPage }: FooterProps = {}) {
  const sharedPage = useLandingHome();
  const effectivePage = cmsPage ?? sharedPage;
  const cmsBlock = findBlock(effectivePage ?? undefined, 'footer');
  const cmsData = (cmsBlock?.data ?? {}) as FooterCmsData;
  const { t } = useTranslation('landing');

  const { openPolicy, openSupport } = useLandingModals();

  const brandTitle = coalesceCmsString(cmsData.brand?.title, t('footer.brandTitle'));
  // 1.50.7: tagline без слов AI / ИИ / нейросеть. Если CMS возвращает
  // legacy-tagline с "AI-фото..." — переписываем на дефолт из i18n,
  // чтобы сайт не рендерил AI-формулировку, пока не задеплоится
  // обновлённый landing_content.json.
  const cmsTagline = asNormString(cmsData.brand?.tagline).trim();
  const defaultTagline = t('footer.tagline');
  const brandTagline =
    cmsTagline && !/\bAI\b|\bИИ\b|нейросет/i.test(cmsTagline)
      ? cmsTagline
      : defaultTagline;

  const products: ProductItem[] = useMemo(() => {
    const fromCms = asProducts(cmsData.products);
    if (fromCms) return fromCms;
    return [
      { label: t('footer.brandTitle'), href: '/' },
      ...listScenariosForFooter(),
    ];
  }, [cmsData.products, t]);

  const supportItems = useMemo(() => {
    const items = asFooterItems(cmsData.support);
    return items.length ? items : buildDefaultSupport(t);
  }, [cmsData.support, t]);

  const documentItems = useMemo(() => {
    const items = asFooterItems(cmsData.documents);
    return items.length ? items : buildDefaultDocuments(t);
  }, [cmsData.documents, t]);

  const socialItems = useMemo(() => {
    const items = asSocialItems(cmsData.social);
    return items.length ? items : buildDefaultSocial(t);
  }, [cmsData.social, t]);

  const creditsText = coalesceCmsString(cmsData.creditsText, t('footer.credits.text'));
  const creditsLinkLabel = coalesceCmsString(cmsData.creditsLinkLabel, t('footer.credits.linkLabel'));
  const creditsLinkHref = coalesceCmsString(cmsData.creditsLinkHref, 'https://ux4ai.pro');
  const copyright = coalesceCmsString(cmsData.copyright, t('footer.copyright'));

  function handleItemClick(item: FooterItem) {
    if (item.action === 'policy') openPolicy(item.policyId);
    else if (item.action === 'support') openSupport();
  }

  function renderItem(item: FooterItem, key: string) {
    const baseClass =
      'text-left text-[14px] leading-[22px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors no-underline cursor-pointer';
    if (item.action === 'link') {
      const isInternal = item.href.startsWith('/') && !(item.external ?? false);
      if (isInternal) {
        return (
          <li key={key}>
            <Link to={item.href} className={baseClass}>
              {item.label}
            </Link>
          </li>
        );
      }
      return (
        <li key={key}>
          <a
            href={item.href}
            {...(item.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            className={baseClass}
          >
            {item.label}
          </a>
        </li>
      );
    }
    return (
      <li key={key}>
        <button
          type="button"
          onClick={() => handleItemClick(item)}
          className={`${baseClass} bg-transparent p-0 border-0`}
        >
          {item.label}
        </button>
      </li>
    );
  }

  const ux4aiLink = socialItems[0]?.href ?? 'https://t.me/ux4ai';

  return (
    <footer className="glass-footer">
      <div className="max-w-[1200px] mx-auto px-[var(--space-16)] tablet:px-[var(--space-24)] py-[var(--space-32)] tablet:py-[var(--space-48)] flex flex-col gap-[var(--space-32)]">
        {/* Top grid: 1col mobile, 2col tablet, 4col desktop */}
        <div className="grid grid-cols-1 tablet:grid-cols-2 desktop:grid-cols-[1.2fr_1fr_1fr_1fr] gap-[var(--space-24)] tablet:gap-[var(--space-32)]">
          {/* Brand column.
              1.50.6: socialItems из левой колонки убраны — ссылка на
              UX4AI-канал теперь живёт только в правой кнопке
              "Подписаться" внизу футера, чтобы не дублировать действие
              в двух местах подряд.
              1.50.7: к названию добавлен LogoEmblem — повторяет шапку
              и закрывает визуальный пробел. */}
          <div className="flex flex-col gap-[var(--space-12)]">
            <div className="flex items-center gap-[var(--space-10)]">
              <div className="relative w-10 h-10 tablet:w-11 tablet:h-11 shrink-0 text-[var(--color-text-primary)]">
                <LogoEmblem className="relative w-full h-full" />
              </div>
              <span className="text-[20px] leading-[28px] font-semibold text-[var(--color-text-primary)] tracking-tight">
                {brandTitle}
              </span>
            </div>
            <p className="text-[14px] leading-[22px] text-[var(--color-text-secondary)] max-w-[320px]">
              {brandTagline}
            </p>
          </div>

          {/* Products column */}
          <div className="flex flex-col">
            <ColumnHeading>{t('footer.groups.products')}</ColumnHeading>
            <ul className="flex flex-col gap-[var(--space-8)]">
              {products.map((p, i) => {
                const isInternal = p.href.startsWith('/') && !p.external;
                // 1.50.6: для внутренних ссылок на лендинги (/, /dokumenty,
                // /znakomstva, /rezume) добавляем scroll-to-top — если
                // пользователь уже на этой странице, Router не
                // перерисует её, и без принудительного scroll клик
                // визуально не реагирует.
                const handleInternalClick = () => {
                  if (typeof window === 'undefined') return;
                  if (window.location.pathname === p.href) {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }
                };
                return (
                  <li key={`${p.href}-${i}`}>
                    {isInternal ? (
                      <Link
                        to={p.href}
                        onClick={handleInternalClick}
                        className="text-[14px] leading-[22px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors no-underline"
                      >
                        {p.label}
                      </Link>
                    ) : (
                      <a
                        href={p.href}
                        {...(p.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                        className="text-[14px] leading-[22px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors no-underline"
                      >
                        {p.label}
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Support column */}
          <div className="flex flex-col">
            <ColumnHeading>{t('footer.groups.support')}</ColumnHeading>
            <ul className="flex flex-col gap-[var(--space-8)]">
              {supportItems.map((item, i) => renderItem(item, `support-${i}`))}
            </ul>
          </div>

          {/* Documents column */}
          <div className="flex flex-col">
            <ColumnHeading>{t('footer.groups.documents')}</ColumnHeading>
            <ul className="flex flex-col gap-[var(--space-8)]">
              {documentItems.map((item, i) => renderItem(item, `doc-${i}`))}
            </ul>
          </div>
        </div>

        {/* Bottom credit row */}
        <div className="flex flex-col tablet:flex-row items-center tablet:items-center justify-between gap-[var(--space-16)] pt-[var(--space-16)] border-t border-white/10">
          <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-8)] tablet:gap-[var(--space-16)] text-[13px] tablet:text-[14px] leading-[22px] text-[var(--color-text-secondary)]">
            <span>{copyright}</span>
            <span className="hidden tablet:inline opacity-40">•</span>
            <span className="inline-flex items-center gap-[var(--space-6)]">
              <span>{creditsText}</span>
              <a
                href={creditsLinkHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-[var(--space-4)] text-[var(--color-text-primary)] hover:text-[var(--color-brand-primary)] transition-colors no-underline"
              >
                <AicaIcon size={14} className="-rotate-45" />
                {creditsLinkLabel}
              </a>
            </span>
          </div>
          <a
            href={ux4aiLink}
            target="_blank"
            rel="noopener noreferrer"
            className="glass-btn-secondary inline-flex items-center gap-[var(--space-8)] px-[var(--space-16)] py-[var(--space-8)] rounded-[var(--radius-pill)] text-[13px] leading-[20px] text-[var(--color-text-primary)] no-underline"
          >
            <TelegramIcon className="text-[var(--color-brand-primary)]" />
            {t('footer.subscribeCta')}
          </a>
        </div>
      </div>

    </footer>
  );
}
