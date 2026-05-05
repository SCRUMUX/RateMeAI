import BeforeAfterSlider from '../components/BeforeAfterSlider';
import { PlaceholderUpload, PlaceholderUpgrade } from '../components/effects/PlaceholderArt';
import { findBlock, type LandingPage } from '../lib/landing-cms';

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

export default function BeforeAfterSection({ cmsPage }: { cmsPage?: LandingPage | null }) {
  const block = findBlock(cmsPage ?? undefined, 'before_after');
  if (!block) return null;
  const data = (block.data ?? {}) as Record<string, unknown>;

  return (
    <section className="relative z-[2] flex flex-col items-center gap-[var(--space-32)] tablet:gap-[var(--space-48)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py">
      <div className="reveal mx-auto flex w-full max-w-[1200px] flex-col items-center gap-[var(--space-12)] text-center">
        <h2 className="landing-h2 text-[var(--color-text-primary)]">
          {asString(data.title, 'До и после')}
        </h2>
        <p className="landing-lead max-w-[720px]">
          {asString(data.caption, 'Перетаскивайте ползунок — результат всегда выглядит естественно.')}
        </p>
      </div>

      <div className="reveal w-full max-w-[820px]">
        <div className="rounded-[var(--radius-12)] overflow-hidden aspect-[3/4]">
          <BeforeAfterSlider
            before={<PlaceholderUpload className="w-full h-full opacity-50 text-[var(--color-text-secondary)]" />}
            after={<PlaceholderUpgrade className="w-full h-full opacity-50 text-[var(--color-text-secondary)]" />}
          />
        </div>
      </div>
    </section>
  );
}

