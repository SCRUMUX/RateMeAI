import { useState } from 'react';
import NavBar from '../sections/NavBar';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import FluidBackground from '../components/effects/FluidBackground';
import EnergyField from '../components/effects/EnergyField';
import ProofCounter from '../sections/ProofCounter';
import Testimonials from '../sections/Testimonials';
import HowItWorks, { type HowItWorksStep } from '../sections/HowItWorks';
import { useApp } from '../context/AppContext';
import { DOCUMENT_SOCIAL_PROOF_PRESET } from '../data/social-proof';
import { DOCUMENT_LANDING_ITEMS } from '../data/landingStyles';
import { REQUIREMENTS_SHORT, REJECT_BULLETS } from '../data/photo-requirements';
import type { Testimonial } from '../data/testimonials';
import useDocumentMeta from '../lib/useDocumentMeta';

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

const STEPS: HowItWorksStep[] = [
  { num: '1', title: 'Загрузите фото', desc: 'Любое фото с чётким лицом, без фильтров и крупным планом — мы проверим автоматически.' },
  { num: '2', title: 'AI-анализ', desc: 'Проверим пригодность фото для документа за несколько секунд.' },
  { num: '3', title: 'Выберите формат', desc: 'Паспорт, виза, права или другой документ — настроим размеры и фон.' },
  { num: '4', title: 'Получите результат', desc: 'Скачайте готовое фото в нужном формате — экономия похода в фотосалон.' },
];

interface LandingProps {
  onStart?: () => void;
  showAuth?: boolean;
  onAuthClose?: () => void;
}

export default function DocumentPhotoLanding({ onStart, showAuth, onAuthClose }: LandingProps) {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);

  const authOpen = authModalOpen || !!showAuth;

  useDocumentMeta({
    title: 'Фото на документы AI · Look Studio',
    description:
      'AI-фото на паспорт, визу и любые документы за 2 минуты: ровный фон, правильный размер, нейтральная мимика — без похода в фотостудию.',
    canonicalPath: '/dokumenty',
  });

  return (
    <div data-category="cv" className="min-h-screen w-full flex flex-col overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} onCtaClick={onStart} hideNavLinks logoTo="/dokumenty" />
      <main className="relative flex-1">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />

        {/* Hero */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] pt-[120px] tablet:pt-[160px] pb-[60px] tablet:pb-[80px] text-center">
          <div className="flex flex-col items-center gap-[var(--space-12)]">
            <span className="text-[48px]">📋</span>
            <h1 className="landing-h1 text-[var(--color-text-primary)] max-w-[700px]">
              Фото на документы
              <br />
              <span style={{
                background: 'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                за 2 минуты
              </span>
            </h1>
            <p className="landing-lead max-w-[520px]">
              AI создаст идеальное фото для паспорта, визы или любого документа. Максимальная фотореалистичность, без лишних эффектов.
            </p>
          </div>

          <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-12)]">
            <button
              onClick={onStart}
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium cursor-pointer"
            >
              Создать фото — 199 ₽
            </button>
            <span className="landing-body text-[var(--color-text-muted)]">5 фото в пакете</span>
          </div>
        </section>

        <ProofCounter
          baseCount={DOCUMENT_SOCIAL_PROOF_PRESET.baseCount}
          counter={DOCUMENT_SOCIAL_PROOF_PRESET.counter}
          heading="Фото для документов уже сделано"
          subheading="Пользователи делают их не выходя из дома и дешевле, чем в студии."
        />

        <Testimonials
          items={DOCUMENT_TESTIMONIALS}
          tone="documents"
        />

        <HowItWorks steps={STEPS} title="Как это работает" />

        {/* Supported formats */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-32)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[80px]">
          <h2 className="landing-h2 text-[var(--color-text-primary)]">Поддерживаемые форматы</h2>
          <div className="grid grid-cols-1 tablet:grid-cols-2 desktop:grid-cols-3 gap-[var(--space-12)] max-w-[900px] w-full">
            {DOCUMENT_LANDING_ITEMS.map((f) => (
              <div key={f.key} className="gradient-border-item glass-row flex items-center gap-[var(--space-12)] px-[var(--space-16)] py-[var(--space-12)] rounded-[var(--radius-12)]"
                style={{ '--gb-color': 'var(--glass-border-hover)' } as React.CSSProperties}
              >
                <span className="text-[24px] shrink-0">{f.icon}</span>
                <div className="flex flex-col min-w-0">
                  <span className="text-[15px] font-medium text-[var(--color-text-primary)]">{f.name}</span>
                  <span className="text-[12px] text-[var(--color-text-muted)]">{f.usage}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Final CTA */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-16)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[80px] text-center">
          <h2 className="landing-h2 text-[var(--color-text-primary)]">
            Готовы создать фото?
          </h2>
          <p className="landing-lead max-w-[400px]">
            Загрузите любое фото и получите результат, соответствующий требованиям документов
          </p>

          <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] w-full max-w-[640px] text-left">
            <div className="flex-1 gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-12)]">
              <p className="text-[13px] font-medium text-[var(--color-text-primary)] mb-[var(--space-6)]">Подходит</p>
              <ul className="flex flex-col gap-[var(--space-4)] text-[12px] leading-[16px] text-[var(--color-text-secondary)]">
                {REQUIREMENTS_SHORT.map((t) => (
                  <li key={t}>• {t}</li>
                ))}
              </ul>
            </div>
            <div className="flex-1 gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-12)]">
              <p className="text-[13px] font-medium text-[var(--color-danger)] mb-[var(--space-6)]">Не будет обработано</p>
              <ul className="flex flex-col gap-[var(--space-4)] text-[12px] leading-[16px] text-[var(--color-text-muted)]">
                {REJECT_BULLETS.slice(0, 4).map((t) => (
                  <li key={t}>• {t}</li>
                ))}
              </ul>
            </div>
          </div>

          <button
            onClick={onStart}
            className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium cursor-pointer"
          >
            Начать
          </button>
        </section>
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
