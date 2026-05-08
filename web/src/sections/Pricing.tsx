import { useState, useRef, useEffect, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { useTranslation } from 'react-i18next';
import { useApp } from '../context/AppContext';
import { createPayment, handleCreatePaymentError } from '../lib/api';
import { normalizePostPaymentPath, getPostPaymentReturnPath } from '../scenarios/config';
import { rememberFlowReturnPath } from '../lib/flow-resume';
import { findBlock, coalesceCmsString, type LandingPage } from '../lib/landing-cms';

function buildDefaultPlans(t: (key: string) => string) {
  return [
    { title: t('pricing.plans.pack5.title'), price: t('pricing.plans.pack5.price'), photos: t('pricing.plans.pack5.photos'), packQty: 5, desc: t('pricing.plans.pack5.desc'), highlighted: false, badge: null as string | null, savingBadge: null as string | null },
    { title: t('pricing.plans.pack10.title'), price: t('pricing.plans.pack10.price'), photos: t('pricing.plans.pack10.photos'), packQty: 10, desc: t('pricing.plans.pack10.desc'), highlighted: true, badge: 'BEST', savingBadge: t('pricing.savingBadge') },
    { title: t('pricing.plans.pack20.title'), price: t('pricing.plans.pack20.price'), photos: t('pricing.plans.pack20.photos'), packQty: 20, desc: t('pricing.plans.pack20.desc'), highlighted: false, badge: null, savingBadge: null },
    { title: t('pricing.plans.pack50.title'), price: t('pricing.plans.pack50.price'), photos: t('pricing.plans.pack50.photos'), packQty: 50, desc: t('pricing.plans.pack50.desc'), highlighted: false, badge: null, savingBadge: null },
  ];
}

type DefaultPlan = ReturnType<typeof buildDefaultPlans>[number];

type CmsPlanRaw = {
  title: unknown;
  price: unknown;
  photos: unknown;
  packQty: unknown;
  desc: unknown;
  highlighted?: unknown;
  badge?: unknown;
  savingBadge?: unknown;
};

type PricingCms = Partial<{
  title: string;
  subtitle: string;
  caption: string;
  tryFreeLabel: string;
  plans: CmsPlanRaw[];
}>;

function asRawPlans(value: unknown): CmsPlanRaw[] | null {
  if (!Array.isArray(value)) return null;
  const out: CmsPlanRaw[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    out.push(item as CmsPlanRaw);
  }
  return out.length ? out : null;
}

function mergePlans(rawPlans: CmsPlanRaw[] | null, defaults: DefaultPlan[]): DefaultPlan[] {
  if (!rawPlans) return defaults;
  // Per-field merge: if CMS field is missing or blank, fall back to the
  // default plan with the same packQty (or same index when packQty does
  // not match anything). This way an empty global JSON renders the
  // English defaults instead of empty cards.
  return rawPlans.map((raw, idx) => {
    const packQtyRaw = typeof raw.packQty === 'number' ? raw.packQty : Number(raw.packQty);
    const packQty = Number.isFinite(packQtyRaw) ? packQtyRaw : defaults[idx]?.packQty ?? idx + 1;
    const fallback = defaults.find((p) => p.packQty === packQty) ?? defaults[idx] ?? defaults[0];
    return {
      title: coalesceCmsString(raw.title, fallback.title),
      price: coalesceCmsString(raw.price, fallback.price),
      photos: coalesceCmsString(raw.photos, fallback.photos),
      packQty,
      desc: coalesceCmsString(raw.desc, fallback.desc),
      highlighted: typeof raw.highlighted === 'boolean' ? raw.highlighted : fallback.highlighted,
      badge: typeof raw.badge === 'string' && raw.badge.trim() ? raw.badge : fallback.badge,
      savingBadge:
        typeof raw.savingBadge === 'string' && raw.savingBadge.trim()
          ? raw.savingBadge
          : fallback.savingBadge,
    } satisfies DefaultPlan;
  });
}

export default function Pricing({ cmsPage }: { cmsPage?: LandingPage | null } = {}) {
  const { canAccessApp } = useApp();
  const navigate = useNavigate();
  const { t } = useTranslation('landing');
  const [loading, setLoading] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const resumePath = getPostPaymentReturnPath() ?? '/app';

  const cmsBlock = findBlock(cmsPage ?? undefined, 'pricing');
  const cmsData = (cmsBlock?.data ?? {}) as PricingCms;
  const defaultPlans = useMemo(() => buildDefaultPlans(t), [t]);
  const rawPlans = useMemo(() => asRawPlans((cmsData as any).plans), [cmsData]);
  const effectivePlans = useMemo(() => mergePlans(rawPlans, defaultPlans), [rawPlans, defaultPlans]);
  const headingTitle = coalesceCmsString(cmsData.title, t('pricing.title'));
  const headingSubtitle = coalesceCmsString(cmsData.subtitle, t('pricing.subtitle'));
  const headingCaption = coalesceCmsString(cmsData.caption, t('pricing.caption'));
  const tryFreeLabel = coalesceCmsString(cmsData.tryFreeLabel, t('pricing.tryFreeLabel'));

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || window.innerWidth >= 768) return;
    const targetIdx = effectivePlans.findIndex(p => p.highlighted);
    if (targetIdx < 0) return;
    requestAnimationFrame(() => {
      const card = el.children[0]?.children[targetIdx] as HTMLElement | undefined;
      if (!card) return;
      const scrollTarget = card.offsetLeft - 20;
      el.scrollTo({ left: scrollTarget, behavior: 'instant' });
    });
  }, [effectivePlans]);

  async function handleBuy(packQty: number) {
    if (!canAccessApp) {
      navigate(resumePath);
      return;
    }
    setLoading(packQty);
    try {
      const next = getPostPaymentReturnPath() ?? normalizePostPaymentPath(window.location.pathname) ?? '/app';
      rememberFlowReturnPath(next);
      const res = await createPayment(packQty);
      window.location.href = res.confirmation_url;
    } catch (e) {
      alert(handleCreatePaymentError(e));
      setLoading(null);
    }
  }

  return (
    <section id="тарифы" className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py"
      style={{ minHeight: '100vh' }}
    >
      {/* Heading */}
      <div className="reveal relative flex flex-col items-center gap-[var(--space-12)] text-center">
        <h2 className="landing-h2 text-[var(--color-text-primary)]">{headingTitle}</h2>
        <h2 className="landing-h2"
          style={{ background: 'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
        >
          {headingSubtitle}
        </h2>
        <p className="landing-lead">{headingCaption}</p>
        <Link
          to={resumePath}
          className="glass-btn-secondary mt-[var(--space-8)] px-[var(--space-16)] tablet:px-[var(--space-20)] py-[var(--space-10)] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-brand-primary)] rounded-[var(--radius-12)] no-underline inline-flex items-center justify-center"
        >
          {tryFreeLabel}
        </Link>
      </div>

      {/* Cards - horizontal scroll on mobile, flex row on desktop */}
      <div
        ref={scrollRef}
        className="relative w-full max-w-[1386px] overflow-x-auto tablet:overflow-x-visible snap-x snap-mandatory tablet:snap-none scrollbar-hide"
        style={{ scrollPaddingInline: '20px' }}
      >
        <div className="reveal-stagger flex items-stretch gap-[var(--space-12)] tablet:gap-[10px] tablet:justify-between px-[20px] tablet:px-0 w-max tablet:w-full">
          {effectivePlans.map((plan, i) => (
            <div key={i}
              className={`snap-center gradient-border-card flex flex-col gap-[var(--space-20)] tablet:gap-[var(--space-32)] p-[var(--space-16)] tablet:p-[var(--space-32)] w-[calc(100vw-56px)] tablet:w-auto min-w-0 tablet:min-w-0 h-auto tablet:h-[480px] rounded-[var(--radius-12)] ${
                plan.highlighted
                  ? 'glass-card-premium flex-none tablet:flex-[1.15]'
                  : 'glass-card flex-none tablet:flex-1'
              }`}
            >
              <div className="flex items-center gap-[var(--space-6)] px-[var(--space-8)] py-[var(--space-4)]">
                <span className="text-[18px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] font-semibold text-[var(--color-text-primary)]">{plan.title}</span>
                {plan.badge && (
                  <span className="glass-badge-info px-[var(--space-6)] py-[2px] text-[12px] font-medium leading-[16px] text-[var(--color-text-primary)] rounded-full">{plan.badge}</span>
                )}
              </div>

              <div className="flex items-center gap-[var(--space-8)] px-[var(--space-8)] py-[var(--space-4)]">
                <CoinIcon size={24} className={plan.highlighted ? 'text-[var(--color-brand-primary)]' : 'text-[var(--color-text-muted)]'} />
                <span className={`text-[20px] tablet:text-[24px] leading-[28px] tablet:leading-[32px] font-medium ${plan.highlighted ? 'text-[var(--color-brand-primary)]' : 'text-[var(--color-text-primary)]'}`}>{plan.price}</span>
              </div>

              <div className="flex items-center gap-[var(--space-8)] px-[var(--space-4)] py-[2px]">
                <ImageIcon size={16} className="text-[var(--color-text-muted)]" />
                <span className="text-[16px] leading-[24px] text-[var(--color-text-secondary)]">{plan.photos}</span>
                {plan.savingBadge && (
                  <span className="glass-badge-danger px-[var(--space-6)] py-[2px] text-[12px] font-medium leading-[16px] text-[var(--color-text-primary)] rounded-full">{plan.savingBadge}</span>
                )}
              </div>

              <p className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] flex-1">{plan.desc}</p>

              <button
                onClick={() => handleBuy(plan.packQty)}
                disabled={loading === plan.packQty}
                className={`w-full px-[var(--space-20)] py-[var(--space-10)] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] rounded-[var(--radius-12)] ${
                  plan.highlighted
                    ? 'glass-btn-primary'
                    : i === effectivePlans.length - 1
                      ? 'glass-btn-secondary font-medium text-[var(--color-brand-primary)]'
                      : 'glass-btn-ghost font-medium'
                }`}
              >
                {loading === plan.packQty ? t('pricing.loading') : t('pricing.select')}
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
