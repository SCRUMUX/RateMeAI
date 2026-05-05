import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import NavBar from '../sections/NavBar';
import Hero from '../sections/Hero';
import HowItWorks from '../sections/HowItWorks';
import Simulation from '../sections/Simulation';
import Pricing from '../sections/Pricing';
import SocialProof from '../sections/SocialProof';
import Footer from '../sections/Footer';
import BeforeAfterSection from '../sections/BeforeAfterSection';
import ApiSection from '../sections/ApiSection';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import FluidBackground from '../components/effects/FluidBackground';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';
import { getLandingSocialProofPreset } from '../data/social-proof';
import { findBlock, useLandingHome } from '../lib/landing-cms';
import useDocumentMeta from '../lib/useDocumentMeta';
import type { SocialProofCounterConfig, SocialProofFeedItem, SocialProofPreset } from '../data/social-proof';
import LogoEmblem from '../assets/LogoEmblem';

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return fallback;
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asCounter(value: unknown): SocialProofCounterConfig | null {
  if (!value || typeof value !== 'object') return null;
  const obj = value as Record<string, unknown>;
  return {
    minDelayMs: asNumber(obj.minDelayMs, 8000),
    maxDelayMs: asNumber(obj.maxDelayMs, 36000),
    burstChance: asNumber(obj.burstChance, 0.16),
    maxBurstSize: asNumber(obj.maxBurstSize, 3),
  };
}

function asFeed(value: unknown): SocialProofFeedItem[] | null {
  if (!Array.isArray(value)) return null;
  const out: SocialProofFeedItem[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const obj = item as Record<string, unknown>;
    const id = asString(obj.id).trim();
    const author = asString(obj.author).trim();
    const message = asString(obj.message).trim();
    const context = asString(obj.context).trim();
    if (!id || !author || !message) continue;
    out.push({ id, author, message, context });
  }
  return out.length ? out : null;
}

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
  const socialProofPreset: SocialProofPreset = useMemo(() => {
    const cmsBlock = findBlock(cmsPage ?? undefined, 'social_proof');
    const data = (cmsBlock?.data ?? {}) as Record<string, unknown>;
    const feed = asFeed(data.feed);
    const counter = asCounter(data.counter);
    if (cmsBlock && feed && counter) {
      return {
        id: app.activeCategory,
        title: asString(data.title, 'Впечатления пользователей'),
        baseCount: asNumber(data.baseCount, 2500),
        counter,
        tickerIntervalMs: asNumber(data.tickerIntervalMs, 4200),
        feed,
      };
    }
    return getLandingSocialProofPreset(app.activeCategory);
  }, [app.activeCategory, cmsPage]);

  return (
    <div data-category={app.activeCategory} className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar
        onLoginClick={() => setAuthModalOpen(true)}
        onCtaClick={canAccessApp ? undefined : () => setAuthModalOpen(true)}
      />
      <main className="relative">
        <MeshGradientBg />
        <FluidBackground />
        <EnergyField />
        <Hero />
        <SocialProof preset={socialProofPreset} />
        <HowItWorks />
        <Simulation cmsPage={cmsPage} />
        <BeforeAfterSection cmsPage={cmsPage} />
        <ApiSection cmsPage={cmsPage} />

        {/* Brand heading + CTA */}
        <section id="app" className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[120px]">
          <div className="relative flex items-center justify-center gap-[var(--space-12)] tablet:gap-[var(--space-24)] w-full max-w-[1200px]">
            <div className="brand-glow-backdrop" />
            <div className="relative w-[60px] h-[60px] tablet:w-[100px] tablet:h-[100px] desktop:w-[140px] desktop:h-[140px] shrink-0 brand-glow-icon text-[var(--color-text-primary)]">
              <LogoEmblem className="relative w-full h-full" />
            </div>
            <span className="brand-glow-text text-[36px] tablet:text-[72px] desktop:text-[120px] leading-[1] font-extrabold whitespace-nowrap">
              Look Studio
            </span>
          </div>

          <div className="flex flex-col items-center gap-[var(--space-16)] text-center max-w-[600px]">
            <h2 className="text-[32px] tablet:text-[48px] font-semibold leading-[1] text-[var(--color-text-primary)]">
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

        <Pricing cmsPage={cmsPage} />
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
