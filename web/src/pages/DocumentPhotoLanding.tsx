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
import { DOCUMENT_SOCIAL_PROOF_PRESET } from '../data/social-proof';
import type { Testimonial } from '../data/testimonials';
import useDocumentMeta, { getCanonicalOrigin } from '../lib/useDocumentMeta';
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

interface RawTestimonial {
  id?: string;
  styleKey?: string;
  category?: string;
  nickname?: string;
  shortReview?: string;
  fullReview?: string;
  emojiReview?: string;
  avatarSeed?: string;
  tier?: 'Обычный' | 'Премиум' | 'Standard' | 'Premium' | string;
}

export default function DocumentPhotoLanding({ onStart, showAuth, onAuthClose }: LandingProps) {
  const app = useApp();
  const canAccessApp = app.canAccessApp;
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const { t: tScenarios } = useTranslation('scenarios');

  const authOpen = authModalOpen || !!showAuth;

  const page = useLandingPage('document_photo');

  const fallbackHero: HeroContent = useMemo(
    () => ({
      icon: tScenarios('documentPhoto.hero.icon'),
      title: tScenarios('documentPhoto.hero.title'),
      gradientPhrase: tScenarios('documentPhoto.hero.gradientPhrase'),
      lead: tScenarios('documentPhoto.hero.lead'),
      ctaLabel: tScenarios('documentPhoto.hero.ctaLabel'),
      ctaMicrocopy: tScenarios('documentPhoto.hero.ctaMicrocopy'),
    }),
    [tScenarios],
  );
  const fallbackProof: ProofCounterContent = useMemo(
    () => ({
      heading: tScenarios('documentPhoto.proof.heading'),
      subheading: tScenarios('documentPhoto.proof.subheading'),
      baseCount: DOCUMENT_SOCIAL_PROOF_PRESET.baseCount,
      counter: DOCUMENT_SOCIAL_PROOF_PRESET.counter,
    }),
    [tScenarios],
  );
  const fallbackHow: HowItWorksContent = useMemo(() => {
    const steps = tScenarios('documentPhoto.how.steps', { returnObjects: true }) as unknown;
    const safeSteps = Array.isArray(steps) ? (steps as HowItWorksContent['steps']) : [];
    return {
      title: tScenarios('documentPhoto.how.title'),
      steps: safeSteps,
    };
  }, [tScenarios]);
  const fallbackFinal: FinalCtaContent = useMemo(
    () => ({
      brandHeading: tScenarios('documentPhoto.final.brandHeading'),
      h2: tScenarios('documentPhoto.final.h2'),
      lead: tScenarios('documentPhoto.final.lead'),
      ctaSignedInLabel: tScenarios('documentPhoto.final.ctaSignedInLabel'),
      ctaAnonymousLabel: tScenarios('documentPhoto.final.ctaAnonymousLabel'),
    }),
    [tScenarios],
  );
  const fallbackPricing: ScenarioPricingContent = useMemo(
    () => ({ tagline: tScenarios('documentPhoto.pricing.tagline') }),
    [tScenarios],
  );

  const documentTestimonials: Testimonial[] = useMemo(() => {
    const raw = tScenarios('documentPhoto.testimonials', { returnObjects: true }) as unknown;
    if (!Array.isArray(raw)) return [];
    return (raw as RawTestimonial[]).map((item) => ({
      id: String(item.id ?? ''),
      styleKey: String(item.styleKey ?? ''),
      category: (item.category as Testimonial['category']) ?? 'cv',
      nickname: String(item.nickname ?? ''),
      shortReview: String(item.shortReview ?? ''),
      fullReview: String(item.fullReview ?? ''),
      emojiReview: String(item.emojiReview ?? ''),
      beforeScore: 0,
      afterScore: 0,
      deltaRange: [0, 0],
      avatarSeed: String(item.avatarSeed ?? item.id ?? ''),
      tier: (item.tier as Testimonial['tier']) ?? 'Обычный',
    }));
  }, [tScenarios]);

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

  // 1.50.7: sync AppContext.activeCategory so portal-mounted modals
  // inherit the correct themed --color-brand-primary token.
  useEffect(() => {
    app.setActiveCategory('cv');
  }, [app]);

  const docLandingJsonLd = useMemo(() => {
    const origin = getCanonicalOrigin();
    return [
      {
        '@context': 'https://schema.org',
        '@type': 'Service',
        name: 'Document photos',
        description:
          'Online photo studio for passport, visa and other document photos. Clean background, correct size, neutral expression in 2 minutes.',
        provider: { '@type': 'Organization', name: 'AI Look Studio', url: origin },
        url: `${origin}/dokumenty`,
      },
      {
        '@context': 'https://schema.org',
        '@type': 'HowTo',
        name: how.title,
        step: how.steps.map((s) => ({ '@type': 'HowToStep', name: s.title, text: s.desc })),
      },
    ];
  }, [how]);

  const { t: tSeo } = useTranslation('seo');
  useDocumentMeta({
    title: tSeo('documentPhoto.title', { defaultValue: 'Фото на документы · Look Studio' }),
    description: tSeo('documentPhoto.description', {
      defaultValue: 'Фото на паспорт, визу и любые документы за 2 минуты: ровный фон, правильный размер, нейтральная мимика — без похода в фотостудию.',
    }),
    canonicalPath: '/dokumenty',
    jsonLd: docLandingJsonLd,
  });

  const howSteps: HowItWorksStep[] = how.steps;

  return (
    <div data-category="cv" className="min-h-screen w-full flex flex-col overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} onCtaClick={onStart} hideNavLinks logoTo="/dokumenty" />
      <main className="relative flex-1">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />

        {/* Hero */}
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

        <Testimonials
          items={documentTestimonials}
          tone="documents"
        />

        <HowItWorks steps={howSteps} title={how.title} />

        <Simulation forceCategory="documents" showCategoryTabs={false} />

        {/* Brand heading + CTA */}
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
