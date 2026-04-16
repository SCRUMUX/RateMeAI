import { useState } from 'react';
import { Link } from 'react-router-dom';
import NavBar from '../sections/NavBar';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';
import { DOCUMENT_FORMAT_ITEMS } from '../scenarios/extraStyles';

const STEPS = [
  { num: '1', title: 'Загрузите фото', desc: 'Любое фото с чётким лицом' },
  { num: '2', title: 'AI-анализ', desc: 'Проверка пригодности за секунды' },
  { num: '3', title: 'Выберите формат', desc: 'Паспорт, виза или другой документ' },
  { num: '4', title: 'Получите результат', desc: 'Скачайте готовое фото' },
];

export default function DocumentPhotoLanding() {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);

  return (
    <div data-category="cv" className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} />
      <main className="relative">
        <MeshGradientBg />
        <EnergyField />

        {/* Hero */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-24)] px-[var(--space-16)] tablet:px-[var(--space-24)] pt-[120px] tablet:pt-[160px] pb-[60px] tablet:pb-[80px] text-center">
          <div className="flex flex-col items-center gap-[var(--space-12)]">
            <span className="text-[48px]">📋</span>
            <h1 className="text-[32px] tablet:text-[48px] desktop:text-[56px] font-semibold leading-[1.1] text-[#E6EEF8] max-w-[700px]">
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
            <p className="text-[16px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] text-[var(--color-text-secondary)] max-w-[520px]">
              AI создаст идеальное фото для паспорта, визы или любого документа. Максимальная фотореалистичность, без лишних эффектов.
            </p>
          </div>

          <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-12)]">
            <Link
              to="/dokumenty"
              className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium no-underline"
            >
              Создать фото — 199 ₽
            </Link>
            <span className="text-[14px] text-[var(--color-text-muted)]">5 фото в пакете</span>
          </div>
        </section>

        {/* How it works */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-32)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[80px]">
          <h2 className="text-[24px] tablet:text-[36px] font-semibold leading-[1.2] text-[#E6EEF8]">Как это работает</h2>
          <div className="grid grid-cols-2 tablet:grid-cols-4 gap-[var(--space-16)] tablet:gap-[var(--space-24)] max-w-[900px]">
            {STEPS.map((s) => (
              <div key={s.num} className="gradient-border-card glass-card flex flex-col items-center gap-[var(--space-8)] p-[var(--space-16)] rounded-[var(--radius-12)] text-center">
                <span className="text-[24px] font-bold" style={{ color: 'rgb(var(--accent-r),var(--accent-g),var(--accent-b))' }}>{s.num}</span>
                <span className="text-[14px] font-medium text-[#E6EEF8]">{s.title}</span>
                <span className="text-[12px] text-[var(--color-text-muted)]">{s.desc}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Supported formats */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-32)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[80px]">
          <h2 className="text-[24px] tablet:text-[36px] font-semibold leading-[1.2] text-[#E6EEF8]">Поддерживаемые форматы</h2>
          <div className="grid grid-cols-1 tablet:grid-cols-2 desktop:grid-cols-3 gap-[var(--space-12)] max-w-[900px] w-full">
            {DOCUMENT_FORMAT_ITEMS.map((f) => (
              <div key={f.key} className="gradient-border-item glass-row flex items-center gap-[var(--space-12)] px-[var(--space-16)] py-[var(--space-12)] rounded-[var(--radius-12)]"
                style={{ '--gb-color': 'rgba(255, 255, 255, 0.10)' } as React.CSSProperties}
              >
                <span className="text-[24px] shrink-0">{f.icon}</span>
                <div className="flex flex-col min-w-0">
                  <span className="text-[15px] font-medium text-[#E6EEF8]">{f.name}</span>
                  <span className="text-[12px] text-[var(--color-text-muted)]">{f.usage}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Final CTA */}
        <section className="relative z-[2] flex flex-col items-center gap-[var(--space-16)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[80px] text-center">
          <h2 className="text-[24px] tablet:text-[36px] font-semibold leading-[1.2] text-[#E6EEF8]">
            Готовы создать фото?
          </h2>
          <p className="text-[16px] text-[var(--color-text-secondary)] max-w-[400px]">
            Загрузите любое фото и получите результат, соответствующий требованиям документов
          </p>
          <Link
            to="/dokumenty"
            className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-32)] py-[var(--space-16)] text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium no-underline"
          >
            Начать
          </Link>
        </section>
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
