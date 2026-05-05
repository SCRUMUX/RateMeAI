import { useState } from 'react';
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

const RESUME_STEPS: HowItWorksStep[] = [
  { num: '1', title: 'Загрузи фото', desc: 'Подойдёт любой портрет — даже домашнее селфи. Главное, чтобы лицо было крупно.' },
  { num: '2', title: 'Выбери стиль', desc: 'Корпоративный, стартап, IT, ментор — подберём под твою сферу.' },
  { num: '3', title: 'Получи результат', desc: 'Профессиональный портрет: спокойный фон, уверенный вайб, без «пластика».' },
  { num: '4', title: 'Усиль профиль', desc: 'Поставь на LinkedIn, hh.ru или резюме — отклики становятся заметнее.' },
];

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

  useDocumentMeta({
    title: 'Фото на резюме AI · Look Studio',
    description:
      'AI-фото для LinkedIn, hh.ru и корпоративных профилей: бизнес-кадрирование, нейтральный фон, естественный костюм. Готово за пару минут.',
    canonicalPath: '/rezume',
  });

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
            <span className="text-[48px]">💼</span>
            <h1 className="landing-h1 text-[var(--color-text-primary)] max-w-[820px]">
              Фото для резюме
              <br />
              <span style={{
                background: 'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                и профиля
              </span>
            </h1>
            <p className="landing-lead max-w-[600px]">
              Сделаем фото собранным и профессиональным: спокойный фон, уверенный вайб, без «пластика» и странных деталей.
            </p>
          </div>

          <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-12)]">
            <button
              onClick={onStart}
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium cursor-pointer"
            >
              Начать
            </button>
            <span className="landing-body text-[var(--color-text-muted)]">Результат за несколько минут</span>
          </div>
        </section>

        <ProofCounter
          baseCount={getLandingSocialProofPreset('cv').baseCount}
          counter={getLandingSocialProofPreset('cv').counter}
          heading="Фото для резюме уже создано"
          subheading="Чтобы вы быстрее нашли работу мечты."
        />

        <Testimonials
          items={getTestimonialsByCategory('cv').slice(0, 4)}
          tone="cv"
        />

        <HowItWorks steps={RESUME_STEPS} title="Как это работает" />

        <Simulation forceCategory="cv" showCategoryTabs={false} />

        {/* Brand heading + CTA */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py">
          <div className="reveal relative flex items-center justify-center gap-[var(--space-16)] tablet:gap-[var(--space-24)] w-full max-w-[1200px]">
            <div className="brand-glow-backdrop" />
            <span className="brand-glow-text text-[32px] tablet:text-[60px] desktop:text-[96px] leading-[1.05] font-extrabold text-center">
              💼 Фото для резюме
            </span>
          </div>

          <div className="reveal flex flex-col items-center gap-[var(--space-16)] text-center max-w-[600px]">
            <h2 className="landing-h2 text-[var(--color-text-primary)]">
              Готовы обновить резюме?
            </h2>
            <p className="landing-lead">
              Замените фото на LinkedIn и hh.ru — отклики на вакансии становятся заметнее
            </p>
            {canAccessApp ? (
              <button
                type="button"
                onClick={onStart}
                className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)] cursor-pointer"
              >
                Открыть приложение
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setAuthModalOpen(true)}
                className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium mt-[var(--space-8)] cursor-pointer"
              >
                Получить доступ
              </button>
            )}
          </div>
        </section>

        <ScenarioPricing tagline="Обнови портрет на LinkedIn и hh.ru за один пакет" />
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

