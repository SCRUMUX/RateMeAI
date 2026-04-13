import { useState } from 'react';
import { Link } from 'react-router-dom';
import NavBar from '../sections/NavBar';
import Hero from '../sections/Hero';
import HowItWorks from '../sections/HowItWorks';
import Simulation from '../sections/Simulation';
import Pricing from '../sections/Pricing';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';

export default function Landing() {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);

  return (
    <div data-category={app.activeCategory} className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} />
      <main className="relative">
        <MeshGradientBg />
        <EnergyField />
        <Hero />
        <HowItWorks />
        <Simulation />

        {/* CTA section — replaces AppScreen */}
        <section id="app" className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] tablet:gap-[var(--space-40)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[120px]">
          <div className="flex flex-col items-center gap-[var(--space-16)] text-center max-w-[600px]">
            <h2 className="text-[32px] tablet:text-[48px] font-semibold leading-[1] text-[#E6EEF8]">
              Попробуйте прямо сейчас
            </h2>
            <p className="text-[16px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] text-[var(--color-text-secondary)]">
              Загрузите фото, получите AI-анализ восприятия и улучшите образ за несколько секунд
            </p>
            <Link
              to="/app"
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium no-underline mt-[var(--space-8)]"
            >
              Открыть приложение
            </Link>
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
