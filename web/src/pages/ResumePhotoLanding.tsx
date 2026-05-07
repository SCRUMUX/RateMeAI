import { useEffect, useMemo, useState } from 'react';
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

const RESUME_FALLBACK_HERO: HeroContent = {
  icon: '💼',
  title: 'Фото для резюме',
  gradientPhrase: 'и профиля',
  lead: 'Сделаем фото собранным и профессиональным: спокойный фон, уверенный вайб, без «пластика» и странных деталей.',
  ctaLabel: 'Начать',
  ctaMicrocopy: 'Результат за несколько минут',
};

const RESUME_FALLBACK_HOW: HowItWorksContent = {
  title: 'Как это работает',
  steps: [
    { num: '1', title: 'Загрузи фото', desc: 'Подойдёт любой портрет — даже домашнее селфи. Главное, чтобы лицо было крупно.' },
    { num: '2', title: 'Выбери стиль', desc: 'Корпоративный, стартап, IT, ментор — подберём под твою сферу.' },
    { num: '3', title: 'Получи результат', desc: 'Профессиональный портрет: спокойный фон, уверенный вайб, без «пластика».' },
    { num: '4', title: 'Усиль профиль', desc: 'Поставь на LinkedIn, hh.ru или резюме — отклики становятся заметнее.' },
  ],
};

const RESUME_FALLBACK_FINAL: FinalCtaContent = {
  brandHeading: '💼 Фото для резюме',
  h2: 'Готовы обновить резюме?',
  lead: 'Замените фото на LinkedIn и hh.ru — отклики на вакансии становятся заметнее',
  ctaSignedInLabel: 'Открыть приложение',
  ctaAnonymousLabel: 'Получить доступ',
};

const RESUME_FALLBACK_PRICING: ScenarioPricingContent = {
  tagline: 'Обнови портрет на LinkedIn и hh.ru за один пакет',
};

interface LandingProps {
  onStart?: () => void;
  showAuth?: boolean;
  onAuthClose?: () => void;
}

export default function ResumePhotoLanding({ onStart, showAuth, onAuthClose }: LandingProps) {
  const app = useApp();
  const canAccessApp = app.canAccessApp;
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const authOpen = authModalOpen || !!showAuth;

  const page = useLandingPage('resume_photo');

  const cvPreset = getLandingSocialProofPreset('cv');
  const fallbackProof: ProofCounterContent = {
    heading: 'Фото для резюме уже создано',
    subheading: 'Чтобы вы быстрее нашли работу мечты.',
    baseCount: cvPreset.baseCount,
    counter: cvPreset.counter,
  };

  const hero = useMemo(
    () => parseHero(findBlock(page, 'hero')?.data, RESUME_FALLBACK_HERO),
    [page],
  );
  const proof = useMemo(
    () => parseProofCounter(findBlock(page, 'proof_counter')?.data, fallbackProof),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [page],
  );
  const how = useMemo(
    () => parseHowItWorks(findBlock(page, 'how_it_works')?.data, RESUME_FALLBACK_HOW),
    [page],
  );
  const final = useMemo(
    () => parseFinalCta(findBlock(page, 'final_cta')?.data, RESUME_FALLBACK_FINAL),
    [page],
  );
  const pricing = useMemo(
    () =>
      parseScenarioPricing(
        findBlock(page, 'scenario_pricing')?.data,
        RESUME_FALLBACK_PRICING,
      ),
    [page],
  );

  // 1.50.7: sync AppContext.activeCategory so portal-mounted modals
  // inherit the correct themed --color-brand-primary token.
  useEffect(() => {
    app.setActiveCategory('cv');
  }, [app]);

  useDocumentMeta({
    title: 'Фото на резюме · Look Studio',
    description:
      'Фото для LinkedIn, hh.ru и корпоративных профилей: бизнес-кадрирование, нейтральный фон, естественный костюм. Готово за пару минут.',
    canonicalPath: '/rezume',
  });

  const howSteps: HowItWorksStep[] = how.steps;

  return (
    <div data-category="cv" className="min-h-screen w-full flex flex-col overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} onCtaClick={onStart} hideNavLinks logoTo="/rezume" />
      <main className="relative flex-1">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />

        {/* Hero */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-hero-py text-center">
          <div className="flex flex-col items-center gap-[var(--space-12)]">
            <span className="text-[48px]">{hero.icon}</span>
            <h1 className="landing-h1 text-[var(--color-text-primary)] max-w-[820px]">
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
            <p className="landing-lead max-w-[600px]">
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
          items={getTestimonialsByCategory('cv').slice(0, 4)}
          tone="cv"
        />

        <HowItWorks steps={howSteps} title={how.title} />

        <Simulation forceCategory="cv" showCategoryTabs={false} />

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
