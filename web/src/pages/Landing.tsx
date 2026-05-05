import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import NavBar from '../sections/NavBar';
import Hero from '../sections/Hero';
import HowItWorks from '../sections/HowItWorks';
import Simulation from '../sections/Simulation';
import Pricing from '../sections/Pricing';
import ProofCounter from '../sections/ProofCounter';
import Testimonials from '../sections/Testimonials';
import Footer from '../sections/Footer';
import BeforeAfterSection from '../sections/BeforeAfterSection';
import ApiSection from '../sections/ApiSection';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import FluidBackground from '../components/effects/FluidBackground';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';
import { TESTIMONIALS, getTestimonialsByCategory } from '../data/testimonials';
import {
  defaultProofCounter,
  findBlock,
  parseProofCounter,
  useLandingHome,
} from '../lib/landing-cms';
import useDocumentMeta from '../lib/useDocumentMeta';
import LogoEmblem from '../assets/LogoEmblem';

export default function Landing() {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const cmsPage = useLandingHome();
  const canAccessApp = app.canAccessApp;

  useDocumentMeta({
    title: 'Look Studio — AI-фото для соцсетей, знакомств, документов и резюме',
    description:
      'AI-фотостудия Look Studio: получите безупречные снимки для Tinder, LinkedIn, паспорта и соцсетей за минуты. Обучаемая модель сохраняет ваше сходство.',
    canonicalPath: '/',
  });

  const proofContent = useMemo(() => {
    const fallback = defaultProofCounter(
      'Классных фото уже создано',
      'В каждой категории — более 100 уникальных стилей под любую задачу.',
      2799,
    );
    const block = findBlock(cmsPage ?? undefined, 'proof_counter');
    return parseProofCounter(block?.data, fallback);
  }, [cmsPage]);

  const testimonialsItems = useMemo(() => {
    const forCategory = getTestimonialsByCategory(app.activeCategory);
    return forCategory.length >= 3 ? forCategory : TESTIMONIALS;
  }, [app.activeCategory]);

  return (
    <div data-category={app.activeCategory} className="min-h-screen w-full flex flex-col overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar
        onLoginClick={() => setAuthModalOpen(true)}
        onCtaClick={canAccessApp ? undefined : () => setAuthModalOpen(true)}
      />
      <main className="relative flex-1">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />
        <Hero />
        <ProofCounter
          baseCount={proofContent.baseCount}
          counter={proofContent.counter}
          heading={proofContent.heading}
          subheading={proofContent.subheading}
        />
        <Testimonials items={testimonialsItems} tone="home" />
        <HowItWorks title="Как это работает" />
        <Simulation cmsPage={cmsPage} />
        <BeforeAfterSection cmsPage={cmsPage} />

        {/* Brand heading + CTA */}
        <section id="app" className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py">
          <div className="reveal relative flex items-center justify-center gap-[var(--space-12)] tablet:gap-[var(--space-24)] w-full max-w-[1200px]">
            <div className="brand-glow-backdrop" />
            <div className="relative w-[60px] h-[60px] tablet:w-[100px] tablet:h-[100px] desktop:w-[140px] desktop:h-[140px] shrink-0 brand-glow-icon text-[var(--color-text-primary)]">
              <LogoEmblem className="relative w-full h-full" />
            </div>
            <span className="brand-glow-text text-[36px] tablet:text-[72px] desktop:text-[120px] leading-[1] font-extrabold whitespace-nowrap">
              Look Studio
            </span>
          </div>

          <div className="reveal flex flex-col items-center gap-[var(--space-16)] text-center max-w-[600px]">
            <h2 className="landing-h2 text-[var(--color-text-primary)]">
              Попробуйте прямо сейчас
            </h2>
            <p className="landing-lead">
              Загрузите фото, получите AI-анализ восприятия и улучшите образ за несколько секунд
            </p>
            {canAccessApp ? (
              <Link
                to="/app"
                className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium no-underline mt-[var(--space-8)]"
              >
                Открыть приложение
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => setAuthModalOpen(true)}
                className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)]"
              >
                Получить доступ
              </button>
            )}
          </div>
        </section>

        <Pricing cmsPage={cmsPage} />

        <ApiSection cmsPage={cmsPage} />
      </main>
      <Footer cmsPage={cmsPage} />

      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onOAuth={async (provider) => {
          await app.loginWithOAuth(provider);
        }}
      />
    </div>
  );
}
