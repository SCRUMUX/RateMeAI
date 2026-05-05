import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import { createPayment, handleCreatePaymentError } from '../lib/api';
import { normalizePostPaymentPath, getPostPaymentReturnPath } from '../scenarios/config';
import { rememberFlowReturnPath } from '../lib/flow-resume';

/**
 * ScenarioPricing — single-tariff variant of the pricing block used
 * on scenario landings (Dating / Resume / Documents). The main
 * landing keeps the 4-card matrix in {@link Pricing}; here we strip
 * down to the "Обновить фото" pack (5 photos, 199 ₽) and present it
 * as a single hero-card centered on the screen.
 *
 * Heading copy mirrors the main Pricing block on purpose so the
 * brand voice stays consistent across all 4 landing pages.
 */

const PACK_QTY = 5;
const PACK_PRICE_LABEL = '199 ₽';
const PACK_PHOTOS_LABEL = '5 AI-фото';

const FEATURES: { icon: string; label: string }[] = [
  { icon: '✦', label: '5 AI-фото в одном пакете' },
  { icon: '✦', label: 'Доступ ко всем стилям категории' },
  { icon: '✦', label: 'Без водяных знаков' },
  { icon: '✦', label: 'Подбор за 2 минуты' },
];

interface ScenarioPricingProps {
  /**
   * Optional tagline shown under the H2 caption. Each landing can
   * pass a scenario-specific copy ("Обнови дейтинг-анкету" etc.).
   * Falls back to the brand-wide line.
   */
  tagline?: string;
}

export default function ScenarioPricing({ tagline }: ScenarioPricingProps) {
  const { canAccessApp } = useApp();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const resumePath = getPostPaymentReturnPath() ?? '/app';

  async function handleBuy() {
    if (!canAccessApp) {
      navigate(resumePath);
      return;
    }
    setLoading(true);
    try {
      const next = getPostPaymentReturnPath() ?? normalizePostPaymentPath(window.location.pathname) ?? '/app';
      rememberFlowReturnPath(next);
      const res = await createPayment(PACK_QTY);
      window.location.href = res.confirmation_url;
    } catch (e) {
      alert(handleCreatePaymentError(e));
      setLoading(false);
    }
  }

  return (
    <section
      id="тарифы"
      className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] py-[60px] tablet:py-[96px]"
    >
      {/* Heading — mirrors main Pricing typography for brand consistency */}
      <div className="reveal flex flex-col items-center gap-[var(--space-12)] text-center max-w-[680px]">
        <h2 className="landing-h2 text-[var(--color-text-primary)]">Первое улучшение</h2>
        <h2
          className="landing-h2"
          style={{
            background:
              'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          — попробуй бесплатно
        </h2>
        <p className="landing-lead">{tagline ?? 'Разблокируй эксклюзивные стили'}</p>
        <Link
          to={resumePath}
          className="glass-btn-secondary mt-[var(--space-8)] px-[var(--space-16)] tablet:px-[var(--space-20)] py-[var(--space-10)] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-brand-primary)] rounded-[var(--radius-12)] no-underline inline-flex items-center justify-center"
        >
          Попробовать бесплатное улучшение
        </Link>
      </div>

      {/* Single highlighted tariff card */}
      <div className="reveal w-full flex justify-center">
        <article
          className="gradient-border-card glass-card-highlight relative flex flex-col gap-[var(--space-24)] p-[var(--space-24)] tablet:p-[var(--space-32)] w-full max-w-[440px] rounded-[var(--radius-16)]"
        >
          <div className="flex items-center justify-between gap-[var(--space-12)]">
            <span className="text-[20px] tablet:text-[22px] leading-[28px] tablet:leading-[30px] font-semibold text-[var(--color-text-primary)]">
              Обновить фото
            </span>
            <span className="glass-badge-info px-[var(--space-8)] py-[2px] text-[12px] font-medium leading-[16px] text-[var(--color-text-primary)] rounded-full">
              5 фото
            </span>
          </div>

          <div className="flex flex-col gap-[var(--space-8)]">
            <div className="flex items-baseline gap-[var(--space-8)]">
              <CoinIcon size={28} className="text-[var(--color-brand-primary)]" />
              <span className="text-[40px] tablet:text-[48px] leading-[1] font-bold text-[var(--color-brand-primary)]">
                {PACK_PRICE_LABEL}
              </span>
            </div>
            <span className="flex items-center gap-[var(--space-6)] text-[14px] leading-[20px] text-[var(--color-text-muted)]">
              <ImageIcon size={14} className="text-[var(--color-text-muted)]" />
              {PACK_PHOTOS_LABEL} · {Math.round(199 / PACK_QTY)} ₽ за фото
            </span>
          </div>

          <ul className="flex flex-col gap-[var(--space-12)] m-0 p-0 list-none">
            {FEATURES.map((f) => (
              <li
                key={f.label}
                className="flex items-start gap-[var(--space-12)] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)]"
              >
                <span
                  aria-hidden
                  className="flex items-center justify-center w-[24px] h-[24px] rounded-full text-[14px] leading-[1] shrink-0"
                  style={{
                    background:
                      'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.12)',
                    color: 'rgb(var(--accent-r), var(--accent-g), var(--accent-b))',
                  }}
                >
                  {f.icon}
                </span>
                <span>{f.label}</span>
              </li>
            ))}
          </ul>

          <button
            type="button"
            onClick={handleBuy}
            disabled={loading}
            className="glass-btn-primary w-full px-[var(--space-20)] py-[var(--space-14)] text-[16px] tablet:text-[18px] leading-[24px] rounded-[var(--radius-12)] font-medium"
          >
            {loading ? 'Загрузка…' : `Купить 5 фото за ${PACK_PRICE_LABEL}`}
          </button>
        </article>
      </div>
    </section>
  );
}
