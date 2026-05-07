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
import { DOCUMENT_SOCIAL_PROOF_PRESET } from '../data/social-proof';
import type { Testimonial } from '../data/testimonials';
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

/**
 * Synthetic, document-flavoured testimonials. The carousel uses the
 * same default 3-slot layout as on other landings; placeholder
 * before/after gets the neutral ``documents`` tone (cream-white,
 * passport-style) so the reader still sees a consistent slider with
 * a thematically distinct visual.
 */
const DOCUMENT_TESTIMONIALS: Testimonial[] = [
  {
    id: 'doc-1',
    styleKey: 'passport',
    category: 'cv',
    nickname: '@anna_paperwork',
    shortReview: 'Сделала фото на загран дома — приняли с первого раза.',
    fullReview: '',
    emojiReview: 'Сделала фото на загран дома 🛂 приняли в МФЦ с первого раза 👌 не тратила время на фотосалон 🙌',
    beforeScore: 0,
    afterScore: 0,
    deltaRange: [0, 0],
    avatarSeed: 'anna_paperwork',
    tier: 'Обычный',
  },
  {
    id: 'doc-2',
    styleKey: 'visa',
    category: 'cv',
    nickname: '@kirill_visa',
    shortReview: 'Виза одобрена, фото прошло проверку требований.',
    fullReview: '',
    emojiReview: 'Виза одобрена ✅ фото прошло проверку с первого раза 📑 спокойный фон и нужные размеры 🎯',
    beforeScore: 0,
    afterScore: 0,
    deltaRange: [0, 0],
    avatarSeed: 'kirill_visa',
    tier: 'Премиум',
  },
  {
    id: 'doc-3',
    styleKey: 'driver_license',
    category: 'cv',
    nickname: '@masha_docs',
    shortReview: 'Удобно, что не надо ехать в фотостудию.',
    fullReview: '',
    emojiReview: 'Не надо ехать в фотостудию 🚗 загрузила селфи — получила фото для прав 📸 быстро и аккуратно 💼',
    beforeScore: 0,
    afterScore: 0,
    deltaRange: [0, 0],
    avatarSeed: 'masha_docs',
    tier: 'Обычный',
  },
  {
    id: 'doc-4',
    styleKey: 'medical',
    category: 'cv',
    nickname: '@oleg_form',
    shortReview: 'Медкомиссия приняла без вопросов.',
    fullReview: '',
    emojiReview: 'Медкомиссия приняла без вопросов 🩺 нейтральный фон и правильные пропорции 📐 экономия времени 🕒',
    beforeScore: 0,
    afterScore: 0,
    deltaRange: [0, 0],
    avatarSeed: 'oleg_form',
    tier: 'Обычный',
  },
];

const FALLBACK_HERO: HeroContent = {
  icon: '📋',
  title: 'Фото на документы',
  gradientPhrase: 'за 2 минуты',
  lead: 'Создадим идеальное фото для паспорта, визы или любого документа. Максимальная фотореалистичность, без лишних эффектов.',
  ctaLabel: 'Создать фото — 199 ₽',
  ctaMicrocopy: '5 фото в пакете',
};

const FALLBACK_PROOF: ProofCounterContent = {
  heading: 'Фото для документов уже сделано',
  subheading: 'Пользователи делают их не выходя из дома и дешевле, чем в студии.',
  baseCount: DOCUMENT_SOCIAL_PROOF_PRESET.baseCount,
  counter: DOCUMENT_SOCIAL_PROOF_PRESET.counter,
};

const FALLBACK_HOW: HowItWorksContent = {
  title: 'Как это работает',
  steps: [
    { num: '1', title: 'Загрузите фото', desc: 'Любое фото с чётким лицом, без фильтров и крупным планом — мы проверим автоматически.' },
    { num: '2', title: 'Проверка фото', desc: 'Проверим пригодность фото для документа за несколько секунд.' },
    { num: '3', title: 'Выберите формат', desc: 'Паспорт, виза, права или другой документ — настроим размеры и фон.' },
    { num: '4', title: 'Получите результат', desc: 'Скачайте готовое фото в нужном формате — экономия похода в фотосалон.' },
  ],
};

const FALLBACK_FINAL: FinalCtaContent = {
  brandHeading: '📋 Фото на документы',
  h2: 'Готовы создать фото?',
  lead: 'Загрузите любое фото — получим результат, соответствующий требованиям документов',
  ctaSignedInLabel: 'Открыть приложение',
  ctaAnonymousLabel: 'Получить доступ',
};

const FALLBACK_PRICING: ScenarioPricingContent = {
  tagline: 'Один пакет — фото на паспорт, визу и любой документ',
};

interface LandingProps {
  onStart?: () => void;
  showAuth?: boolean;
  onAuthClose?: () => void;
}

export default function DocumentPhotoLanding({ onStart, showAuth, onAuthClose }: LandingProps) {
  const app = useApp();
  const canAccessApp = app.canAccessApp;
  const [authModalOpen, setAuthModalOpen] = useState(false);

  const authOpen = authModalOpen || !!showAuth;

  const page = useLandingPage('document_photo');

  const hero = useMemo(
    () => parseHero(findBlock(page, 'hero')?.data, FALLBACK_HERO),
    [page],
  );
  const proof = useMemo(
    () => parseProofCounter(findBlock(page, 'proof_counter')?.data, FALLBACK_PROOF),
    [page],
  );
  const how = useMemo(
    () => parseHowItWorks(findBlock(page, 'how_it_works')?.data, FALLBACK_HOW),
    [page],
  );
  const final = useMemo(
    () => parseFinalCta(findBlock(page, 'final_cta')?.data, FALLBACK_FINAL),
    [page],
  );
  const pricing = useMemo(
    () =>
      parseScenarioPricing(
        findBlock(page, 'scenario_pricing')?.data,
        FALLBACK_PRICING,
      ),
    [page],
  );

  // 1.50.7: sync AppContext.activeCategory so portal-mounted modals
  // inherit the correct themed --color-brand-primary token.
  useEffect(() => {
    app.setActiveCategory('cv');
  }, [app]);

  useDocumentMeta({
    title: 'Фото на документы · Look Studio',
    description:
      'Фото на паспорт, визу и любые документы за 2 минуты: ровный фон, правильный размер, нейтральная мимика — без похода в фотостудию.',
    canonicalPath: '/dokumenty',
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
          items={DOCUMENT_TESTIMONIALS}
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
