import { findBlock, type LandingPage } from '../lib/landing-cms';

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asUrl(value: unknown, fallback = ''): string {
  const s = typeof value === 'string' ? value.trim() : '';
  return s || fallback;
}

export default function ApiSection({ cmsPage }: { cmsPage?: LandingPage | null }) {
  const block = findBlock(cmsPage ?? undefined, 'api');
  if (!block) return null;
  const data = (block.data ?? {}) as Record<string, unknown>;

  const title = asString(data.title, 'API для интеграций');
  const subtitle = asString(data.subtitle, 'Подключайте AI-анализ и генерацию в свои продукты');
  const primaryLabel = asString(data.primaryCtaLabel, 'Открыть документацию');
  const primaryUrl = asUrl(data.primaryCtaUrl, '/api/v1/docs');
  const secondaryLabel = asString(data.secondaryCtaLabel, '');
  const secondaryUrl = asUrl(data.secondaryCtaUrl, '');

  const isExternal = (url: string) => /^https?:\/\//i.test(url) || url.startsWith('mailto:');

  return (
    <section id="api" className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[88px]">
      <div className="mx-auto w-full max-w-[1200px]">
        <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-16)] tablet:p-[var(--space-24)] flex flex-col tablet:flex-row items-start tablet:items-center justify-between gap-[var(--space-16)]">
          <div className="flex flex-col gap-[var(--space-8)]">
            <h2 className="text-[24px] tablet:text-[32px] font-semibold leading-[1.1] text-[var(--color-text-primary)]">
              {title}
            </h2>
            <p className="text-[14px] tablet:text-[16px] leading-[22px] text-[var(--color-text-secondary)] max-w-[720px]">
              {subtitle}
            </p>
          </div>

          <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] w-full tablet:w-auto">
            <a
              href={primaryUrl}
              {...(isExternal(primaryUrl) ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[22px] rounded-[var(--radius-12)] font-medium no-underline"
            >
              {primaryLabel}
            </a>
            {secondaryLabel && secondaryUrl && (
              <a
                href={secondaryUrl}
                {...(isExternal(secondaryUrl) ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                className="glass-btn-secondary inline-flex items-center justify-center px-[var(--space-24)] py-[var(--space-12)] text-[16px] leading-[22px] rounded-[var(--radius-12)] font-medium no-underline text-[var(--color-brand-primary)]"
              >
                {secondaryLabel}
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

