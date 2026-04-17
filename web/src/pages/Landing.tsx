import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import NavBar from '../sections/NavBar';
import Hero from '../sections/Hero';
import HowItWorks from '../sections/HowItWorks';
import Simulation from '../sections/Simulation';
import Pricing from '../sections/Pricing';
import SocialProof from '../sections/SocialProof';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';
import { getLandingSocialProofPreset } from '../data/social-proof';
import logoSrc from '../assets/logo.png';

export default function Landing() {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const canAccessApp = app.canAccessApp;
  const socialProofPreset = useMemo(
    () => getLandingSocialProofPreset(app.activeCategory),
    [app.activeCategory],
  );

  return (
    <div data-category={app.activeCategory} className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar
        onLoginClick={() => setAuthModalOpen(true)}
        onCtaClick={canAccessApp ? undefined : () => setAuthModalOpen(true)}
      />
      <main className="relative">
        <MeshGradientBg />
        <EnergyField />
        <Hero />
        <SocialProof preset={socialProofPreset} />
        <HowItWorks />
        <Simulation />

        {/* Brand heading + CTA */}
        <section id="app" className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[120px]">
          <div className="relative flex items-center justify-center gap-[var(--space-12)] tablet:gap-[var(--space-24)] w-full max-w-[1200px]">
            <div className="brand-glow-backdrop" />
            <div className="relative w-[60px] h-[60px] tablet:w-[100px] tablet:h-[100px] desktop:w-[140px] desktop:h-[140px] shrink-0 brand-glow-icon">
              <div className="absolute inset-0 rounded-[16px] tablet:rounded-[24px] desktop:rounded-[28px]" style={{ background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.4)' }} />
              <img src={logoSrc} alt="AI Look Studio" className="relative w-full h-full object-contain rounded-[16px] tablet:rounded-[24px] desktop:rounded-[28px]" style={{ mixBlendMode: 'lighten' }} />
            </div>
            <span className="brand-glow-text text-[36px] tablet:text-[72px] desktop:text-[120px] leading-[1] font-extrabold whitespace-nowrap">
              AI Look Studio
            </span>
          </div>

          <div className="flex flex-col items-center gap-[var(--space-16)] text-center max-w-[600px]">
            <h2 className="text-[32px] tablet:text-[48px] font-semibold leading-[1] text-[#E6EEF8]">
              Попробуйте прямо сейчас
            </h2>
            <p className="text-[16px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] text-[var(--color-text-secondary)]">
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

        <Pricing />
      </main>
      <Footer />

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
