import { useState } from 'react';
import NavBar from '../sections/NavBar';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import FluidBackground from '../components/effects/FluidBackground';
import EnergyField from '../components/effects/EnergyField';
import ProofCounter from '../sections/ProofCounter';
import { useApp } from '../context/AppContext';
import { getLandingSocialProofPreset } from '../data/social-proof';
import useDocumentMeta from '../lib/useDocumentMeta';

interface LandingProps {
  onStart?: () => void;
  showAuth?: boolean;
  onAuthClose?: () => void;
}

export default function DatingPhotoLanding({ onStart, showAuth, onAuthClose }: LandingProps) {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const authOpen = authModalOpen || !!showAuth;

  useDocumentMeta({
    title: 'Фото для знакомств AI · Look Studio',
    description:
      'AI-фото для Tinder, Hinge и Bumble: естественные снимки, которые увеличивают мэтчи. Сохраняем сходство, добавляем свет, мимику и кадрирование.',
    canonicalPath: '/znakomstva',
  });

  return (
    <div data-category="dating" className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} onCtaClick={onStart} hideNavLinks logoTo="/znakomstva" />
      <main className="relative">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />

        {/* Hero */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] pt-[120px] tablet:pt-[160px] pb-[60px] tablet:pb-[80px] text-center">
          <div className="flex flex-col items-center gap-[var(--space-12)]">
            <span className="text-[48px]">💘</span>
            <h1 className="text-[32px] tablet:text-[48px] desktop:text-[56px] font-semibold leading-[1.1] text-[var(--color-text-primary)] max-w-[760px]">
              Фото для знакомств
              <br />
              <span style={{
                background: 'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                чтобы отвечали чаще
              </span>
            </h1>
            <p className="text-[16px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] text-[var(--color-text-secondary)] max-w-[560px]">
              Улучшим фото так, чтобы оно выглядело естественно, дружелюбно и уверенно — без эффекта «перегенерировано».
            </p>
          </div>

          <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-12)]">
            <button
              onClick={onStart}
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium cursor-pointer"
            >
              Начать
            </button>
            <span className="text-[14px] text-[var(--color-text-muted)]">Займёт пару минут</span>
          </div>
        </section>

        <ProofCounter
          baseCount={getLandingSocialProofPreset('dating').baseCount}
          counter={getLandingSocialProofPreset('dating').counter}
          eyebrow="Знакомства"
          caption="классных AI-фото для знакомств — чтобы вы быстрее нашли свою половинку"
          subcaption="Естественно, дружелюбно, без эффекта «перегенерировано»."
        />
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

