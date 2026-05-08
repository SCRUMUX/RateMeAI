import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import NavBar from '../sections/NavBar';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import FluidBackground from '../components/effects/FluidBackground';
import EnergyField from '../components/effects/EnergyField';
import ProofCounter from '../sections/ProofCounter';
import HowItWorks, { type HowItWorksStep } from '../sections/HowItWorks';
import ScenarioPricing from '../sections/ScenarioPricing';
import { useApp } from '../context/AppContext';
import { DOCUMENT_SOCIAL_PROOF_PRESET } from '../data/social-proof';
import useDocumentMeta from '../lib/useDocumentMeta';
import {
  findBlock,
  parseFinalCta,
  parseHero,
  parseHowItWorks,
  parseProofCounter,
  parseScenarioPricing,
  useLandingPage,
  type FinalCtaContent,
  type HeroContent,
  type HowItWorksContent,
  type ProofCounterContent,
  type ScenarioPricingContent,
} from '../lib/landing-cms';
import type { VisaScenarioMeta } from '../scenarios/visas';

/**
 * Generic visa landing. Identical structure to DocumentPhotoLanding —
 * hero / proof / how-it-works / final CTA / scenario pricing — but
 * parametrised on a ``VisaScenarioMeta`` so all 10+ visas share one
 * component instead of forking copies.
 *
 * Copy comes from three layers, in order of priority:
 *   1. ``data/landing_content.json`` page = ``visa.landingSlug``
 *      (admin-editable, per-server localisation),
 *   2. i18n fallbacks (``wizard:scenario.labels.<slug>``,
 *      ``seo:visa.title|description``),
 *   3. hardcoded fallback strings (RU, ship-safe).
 */

interface Props {
  visa: VisaScenarioMeta;
  onStart?: () => void;
  showAuth?: boolean;
  onAuthClose?: () => void;
}

export default function VisaLanding({ visa, onStart, showAuth, onAuthClose }: Props) {
  const app = useApp();
  const canAccessApp = app.canAccessApp;
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const authOpen = authModalOpen || !!showAuth;
  const { t } = useTranslation(['wizard', 'seo', 'common', 'landing', 'scenarios']);

  const page = useLandingPage(visa.landingSlug);

  const country = t(visa.countryLabelKey);
  const sizeLabel = t('scenarios:visa.sizeFormat', { w: visa.sizeMm[0], h: visa.sizeMm[1] });

  const fallbackHero: HeroContent = useMemo(
    () => ({
      icon: visa.icon,
      title: country,
      gradientPhrase: t('scenarios:visa.gradientPhrase', { size: sizeLabel }),
      lead: t('seo:visa.description', { country }),
      ctaLabel: t('common:cta.createPhoto'),
      ctaMicrocopy: t('common:cta.tryFree'),
    }),
    [country, sizeLabel, visa.icon, t],
  );

  const fallbackProof: ProofCounterContent = useMemo(
    () => ({
      heading: t('landing:visa.fallbackProof.heading'),
      subheading: t('landing:visa.fallbackProof.subheading'),
      baseCount: DOCUMENT_SOCIAL_PROOF_PRESET.baseCount,
      counter: DOCUMENT_SOCIAL_PROOF_PRESET.counter,
    }),
    [t],
  );

  const fallbackHow: HowItWorksContent = useMemo(
    () => ({
      title: t('landing:visa.fallbackHow.title'),
      steps: [
        { num: '1', title: t('landing:visa.fallbackHow.step1Title'), desc: t('landing:visa.fallbackHow.step1Desc') },
        { num: '2', title: t('landing:visa.fallbackHow.step2Title'), desc: t('landing:visa.fallbackHow.step2Desc') },
        { num: '3', title: t('landing:visa.fallbackHow.step3Title'), desc: t('landing:visa.fallbackHow.step3Desc') },
        { num: '4', title: t('landing:visa.fallbackHow.step4Title'), desc: t('landing:visa.fallbackHow.step4Desc') },
      ],
    }),
    [t],
  );

  const fallbackFinal: FinalCtaContent = useMemo(
    () => ({
      brandHeading: `${visa.icon} ${country}`,
      h2: t('landing:visa.fallbackFinal.h2'),
      lead: t('landing:visa.fallbackFinal.lead'),
      ctaSignedInLabel: t('common:cta.openApp'),
      ctaAnonymousLabel: t('common:cta.getAccess'),
    }),
    [country, visa.icon, t],
  );

  const fallbackPricing: ScenarioPricingContent = useMemo(
    () => ({ tagline: t('landing:visa.fallbackPricing.tagline') }),
    [t],
  );

  const hero = useMemo(
    () => parseHero(findBlock(page, 'hero')?.data, fallbackHero),
    [page, fallbackHero],
  );
  const proof = useMemo(
    () => parseProofCounter(findBlock(page, 'proof_counter')?.data, fallbackProof),
    [page, fallbackProof],
  );
  const how = useMemo(
    () => parseHowItWorks(findBlock(page, 'how_it_works')?.data, fallbackHow),
    [page, fallbackHow],
  );
  const final = useMemo(
    () => parseFinalCta(findBlock(page, 'final_cta')?.data, fallbackFinal),
    [page, fallbackFinal],
  );
  const pricing = useMemo(
    () => parseScenarioPricing(findBlock(page, 'scenario_pricing')?.data, fallbackPricing),
    [page, fallbackPricing],
  );

  useEffect(() => {
    app.setActiveCategory('cv');
  }, [app]);

  // JSON-LD: ``Service`` schema describes the visa-photo offering,
  // ``HowTo`` mirrors the how-it-works section. Both help Google +
  // Yandex understand what the page is about beyond og:title.
  const jsonLd = useMemo(() => {
    const canonical = `https://ailookstudio.ru/visa/${visa.countrySlug}`;
    return [
      {
        '@context': 'https://schema.org',
        '@type': 'Service',
        name: t('seo:visa.title', { country }),
        description: t('seo:visa.description', { country }),
        provider: { '@type': 'Organization', name: 'AI Look Studio', url: 'https://ailookstudio.ru' },
        areaServed: country,
        url: canonical,
      },
      {
        '@context': 'https://schema.org',
        '@type': 'HowTo',
        name: how.title,
        step: how.steps.map((s) => ({ '@type': 'HowToStep', name: s.title, text: s.desc })),
      },
    ];
  }, [country, visa.countrySlug, how, t]);

  useDocumentMeta({
    title: t('seo:visa.title', { country }),
    description: t('seo:visa.description', { country }),
    canonicalPath: `/visa/${visa.countrySlug}`,
    jsonLd,
  });

  const howSteps: HowItWorksStep[] = how.steps;

  return (
    <div data-category="cv" className="min-h-screen w-full flex flex-col overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} onCtaClick={onStart} hideNavLinks logoTo={`/visa/${visa.countrySlug}`} />
      <main className="relative flex-1">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />

        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-hero-py text-center">
          <div className="flex flex-col items-center gap-[var(--space-12)]">
            <span className="text-[48px]">{hero.icon}</span>
            <h1 className="landing-h1 text-[var(--color-text-primary)] max-w-[700px]">
              {hero.title}
              <br />
              <span style={{
                background: 'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                {hero.gradientPhrase}
              </span>
            </h1>
            <p className="landing-lead max-w-[520px]">
              {hero.lead}
            </p>
          </div>

          <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-12)]">
            <button
              onClick={onStart}
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium cursor-pointer"
            >
              {hero.ctaLabel}
            </button>
            <span className="landing-body text-[var(--color-text-muted)]">{hero.ctaMicrocopy}</span>
          </div>
        </section>

        <ProofCounter
          baseCount={proof.baseCount}
          counter={proof.counter}
          heading={proof.heading}
          subheading={proof.subheading}
        />

        <HowItWorks steps={howSteps} title={how.title} />

        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py">
          <div className="reveal relative flex items-center justify-center gap-[var(--space-16)] tablet:gap-[var(--space-24)] w-full max-w-[1200px]">
            <div className="brand-glow-backdrop" />
            <span className="brand-glow-text text-[32px] tablet:text-[60px] desktop:text-[96px] leading-[1.05] font-extrabold text-center">
              {final.brandHeading}
            </span>
          </div>

          <div className="reveal flex flex-col items-center gap-[var(--space-16)] text-center max-w-[600px]">
            <h2 className="landing-h2 text-[var(--color-text-primary)]">
              {final.h2}
            </h2>
            <p className="landing-lead">
              {final.lead}
            </p>
            {canAccessApp ? (
              <button
                type="button"
                onClick={onStart}
                className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)] cursor-pointer"
              >
                {final.ctaSignedInLabel}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setAuthModalOpen(true)}
                className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)] cursor-pointer"
              >
                {final.ctaAnonymousLabel}
              </button>
            )}
          </div>
        </section>

        <ScenarioPricing tagline={pricing.tagline} />
      </main>
      <Footer />

      <AuthModal
        open={authOpen}
        onClose={() => { setAuthModalOpen(false); onAuthClose?.(); }}
        onOAuth={async (provider) => {
          await app.loginWithOAuth(provider);
        }}
      />
    </div>
  );
}
