import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import NavBar from '../sections/NavBar';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import FluidBackground from '../components/effects/FluidBackground';
import EnergyField from '../components/effects/EnergyField';
import ProofCounter from '../sections/ProofCounter';
import Testimonials from '../sections/Testimonials';
import Simulation from '../sections/Simulation';
import HowItWorks, { type HowItWorksStep } from '../sections/HowItWorks';
import ScenarioPricing from '../sections/ScenarioPricing';
import { useApp } from '../context/AppContext';
import { getLandingSocialProofPreset } from '../data/social-proof';
import { getTestimonialsByCategory } from '../data/testimonials';
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

interface LandingProps {
  onStart?: () => void;
  showAuth?: boolean;
  onAuthClose?: () => void;
}

export default function DatingPhotoLanding({ onStart, showAuth, onAuthClose }: LandingProps) {
  const app = useApp();
  const canAccessApp = app.canAccessApp;
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const authOpen = authModalOpen || !!showAuth;
  const { t: tScenarios } = useTranslation('scenarios');

  const page = useLandingPage('dating_photo');

  const datingPreset = getLandingSocialProofPreset('dating');

  const fallbackHero: HeroContent = useMemo(
    () => ({
      icon: tScenarios('dating.hero.icon'),
      title: tScenarios('dating.hero.title'),
      gradientPhrase: tScenarios('dating.hero.gradientPhrase'),
      lead: tScenarios('dating.hero.lead'),
      ctaLabel: tScenarios('dating.hero.ctaLabel'),
      ctaMicrocopy: tScenarios('dating.hero.ctaMicrocopy'),
    }),
    [tScenarios],
  );
  const fallbackProof: ProofCounterContent = useMemo(
    () => ({
      heading: tScenarios('dating.proof.heading'),
      subheading: tScenarios('dating.proof.subheading'),
      baseCount: datingPreset.baseCount,
      counter: datingPreset.counter,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tScenarios],
  );
  const fallbackHow: HowItWorksContent = useMemo(() => {
    const steps = tScenarios('dating.how.steps', { returnObjects: true }) as unknown;
    const safe = Array.isArray(steps) ? (steps as HowItWorksContent['steps']) : [];
    return {
      title: tScenarios('dating.how.title'),
      steps: safe,
    };
  }, [tScenarios]);
  const fallbackFinal: FinalCtaContent = useMemo(
    () => ({
      brandHeading: tScenarios('dating.final.brandHeading'),
      h2: tScenarios('dating.final.h2'),
      lead: tScenarios('dating.final.lead'),
      ctaSignedInLabel: tScenarios('dating.final.ctaSignedInLabel'),
      ctaAnonymousLabel: tScenarios('dating.final.ctaAnonymousLabel'),
    }),
    [tScenarios],
  );
  const fallbackPricing: ScenarioPricingContent = useMemo(
    () => ({ tagline: tScenarios('dating.pricing.tagline') }),
    [tScenarios],
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
    () =>
      parseScenarioPricing(
        findBlock(page, 'scenario_pricing')?.data,
        fallbackPricing,
      ),
    [page, fallbackPricing],
  );

  // 1.50.7: sync AppContext.activeCategory with the page's themed
  // category so portal-mounted modals (Policy/Support/Auth/Storage)
  // inherit the right --color-brand-primary token.
  useEffect(() => {
    app.setActiveCategory('dating');
  }, [app]);

  useDocumentMeta({
    title: tScenarios('dating.seo.title'),
    description: tScenarios('dating.seo.description'),
    canonicalPath: '/znakomstva',
  });

  const howSteps: HowItWorksStep[] = how.steps;

  return (
    <div data-category="dating" className="min-h-screen w-full flex flex-col overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} onCtaClick={onStart} hideNavLinks logoTo="/znakomstva" />
      <main className="relative flex-1">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />

        {/* Hero */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-hero-py text-center">
          <div className="flex flex-col items-center gap-[var(--space-12)]">
            <span className="text-[48px]">{hero.icon}</span>
            <h1 className="landing-h1 text-[var(--color-text-primary)] max-w-[760px]">
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
            <p className="landing-lead max-w-[560px]">
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

        <Testimonials
          items={getTestimonialsByCategory('dating').slice(0, 4)}
          tone="dating"
        />

        <HowItWorks steps={howSteps} title={how.title} />

        <Simulation forceCategory="dating" showCategoryTabs={false} />

        {/* Brand heading + CTA — повторяет section#app основного
            лендинга, но без логотипа Look Studio: вместо него крупная
            надпись с темой сценария. */}
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
