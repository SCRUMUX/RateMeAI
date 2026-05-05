import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import { createPayment, handleCreatePaymentError } from '../lib/api';
import { normalizePostPaymentPath, getPostPaymentReturnPath } from '../scenarios/config';
import { rememberFlowReturnPath } from '../lib/flow-resume';

/**
 * ScenarioPricing — финальный экран сценарных лендингов
 * (Dating / Resume / Documents). На основном лендинге используется
 * полноразмерный Pricing с 4 карточками; здесь — три позиции,
 * заточенные под сценарный конверт-flow:
 *
 *   1. «Попробовать»     — 199 ₽ · 5 фото           (glass-card)
 *   2. «Прокачать образ» — 499 ₽ · 15 фото · BEST   (glass-card-premium)
 *   3. «Корпоративный»   — B2B-карточка без цены    (glass-card)
 *
 * Карточка #3 ведёт на главный лендинг к секции <ApiSection /> —
 * аналогично NavBar.scrollToPricing: если мы уже на «/», просто
 * scrollIntoView; если на сценарном — navigate('/') + setTimeout
 * 100 ms + scrollIntoView (пока React успевает отрисовать раздел).
 *
 * 1.50.4: visual-язык унифицирован с шапкой через .glass-card-premium
 * + sheen (см. index.css). Hover-lift включён глобально.
 */

type PackQty = 5 | 15;

interface PaidPlan {
  id: 'try' | 'pro';
  packQty: PackQty;
  title: string;
  priceLabel: string;
  photosLabel: string;
  perPhotoLabel: string;
  desc: string;
  features: string[];
  highlighted: boolean;
  badge?: string;
  savingBadge?: string;
  ctaLabel: string;
}

const PAID_PLANS: PaidPlan[] = [
  {
    id: 'try',
    packQty: 5,
    title: 'Попробовать',
    priceLabel: '199 ₽',
    photosLabel: '5 AI-фото',
    perPhotoLabel: '40 ₽ за фото',
    desc: 'Стартовый пакет — оцени, как AI работает с твоим лицом.',
    features: ['Доступ ко всем стилям категории', 'Без водяных знаков', 'Подбор за 2 минуты'],
    highlighted: false,
    ctaLabel: 'Купить 5 за 199 ₽',
  },
  {
    id: 'pro',
    packQty: 15,
    title: 'Прокачать образ',
    priceLabel: '499 ₽',
    photosLabel: '15 AI-фото',
    perPhotoLabel: '33 ₽ за фото',
    desc: 'Полный сет под анкету, резюме или документы — хватит на все ситуации.',
    features: ['15 фото в одном пакете', 'Все стили + эксклюзивы', 'Приоритетная очередь генерации', 'Без водяных знаков'],
    highlighted: true,
    badge: 'BEST',
    savingBadge: 'Экономия 40%',
    ctaLabel: 'Купить 15 за 499 ₽',
  },
];

const CORPORATE_FEATURES = [
  '✦ Свой бренд и кастомные стили',
  '✦ Webhook-интеграция и SDK',
  '✦ SLA, договор и счёт',
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
  const [loading, setLoading] = useState<PackQty | null>(null);
  const resumePath = getPostPaymentReturnPath() ?? '/app';

  async function handleBuy(packQty: PackQty) {
    if (!canAccessApp) {
      navigate(resumePath);
      return;
    }
    setLoading(packQty);
    try {
      const next = getPostPaymentReturnPath() ?? normalizePostPaymentPath(window.location.pathname) ?? '/app';
      rememberFlowReturnPath(next);
      const res = await createPayment(packQty);
      window.location.href = res.confirmation_url;
    } catch (e) {
      alert(handleCreatePaymentError(e));
      setLoading(null);
    }
  }

  /**
   * Переход на /#api с гарантированным scroll-to-anchor: если мы
   * уже на главной — scrollIntoView; иначе — navigate + setTimeout
   * (как в NavBar.scrollToPricing).
   */
  function handleCorporate() {
    if (typeof window !== 'undefined' && window.location.pathname === '/') {
      document.getElementById('api')?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    navigate('/');
    setTimeout(() => {
      document.getElementById('api')?.scrollIntoView({ behavior: 'smooth' });
    }, 120);
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

      {/* Cards row: 2 paid + 1 corporate.
          Mobile: horizontal snap-scroll (как в основном Pricing).
          Desktop: 3-up grid, центральная карточка чуть шире. */}
      <div
        className="reveal-stagger relative w-full max-w-[1200px] overflow-x-auto tablet:overflow-x-visible snap-x snap-mandatory tablet:snap-none scrollbar-hide"
        style={{ scrollPaddingInline: '20px' }}
      >
        <div className="flex items-stretch gap-[var(--space-12)] tablet:gap-[var(--space-16)] tablet:justify-between px-[20px] tablet:px-0 w-max tablet:w-full">
          {/* Paid plans */}
          {PAID_PLANS.map((plan) => (
            <article
              key={plan.id}
              className={`snap-center gradient-border-card flex flex-col gap-[var(--space-20)] tablet:gap-[var(--space-24)] p-[var(--space-20)] tablet:p-[var(--space-28)] w-[calc(100vw-56px)] tablet:w-auto min-w-0 tablet:min-w-0 h-auto tablet:min-h-[520px] rounded-[var(--radius-16)] ${
                plan.highlighted
                  ? 'glass-card-premium flex-none tablet:flex-[1.15]'
                  : 'glass-card flex-none tablet:flex-1'
              }`}
            >
              {/* Title + BEST badge */}
              <div className="flex items-center justify-between gap-[var(--space-12)]">
                <span className="text-[20px] tablet:text-[22px] leading-[28px] tablet:leading-[30px] font-semibold text-[var(--color-text-primary)]">
                  {plan.title}
                </span>
                {plan.badge && (
                  <span className="glass-badge-info px-[var(--space-8)] py-[2px] text-[12px] font-medium leading-[16px] text-[var(--color-text-primary)] rounded-full">
                    {plan.badge}
                  </span>
                )}
              </div>

              {/* Price block */}
              <div className="flex flex-col gap-[var(--space-8)]">
                <div className="flex items-baseline gap-[var(--space-8)]">
                  <CoinIcon size={28} className="text-[var(--color-brand-primary)]" />
                  <span className="text-[36px] tablet:text-[44px] leading-[1] font-bold text-[var(--color-brand-primary)]">
                    {plan.priceLabel}
                  </span>
                </div>
                <span className="flex items-center gap-[var(--space-6)] text-[14px] leading-[20px] text-[var(--color-text-muted)]">
                  <ImageIcon size={14} className="text-[var(--color-text-muted)]" />
                  {plan.photosLabel} · {plan.perPhotoLabel}
                  {plan.savingBadge && (
                    <span className="glass-badge-danger ml-[var(--space-4)] px-[var(--space-6)] py-[2px] text-[11px] font-medium leading-[14px] text-[var(--color-text-primary)] rounded-full">
                      {plan.savingBadge}
                    </span>
                  )}
                </span>
              </div>

              {/* Short desc */}
              <p className="text-[14px] tablet:text-[15px] leading-[20px] tablet:leading-[22px] text-[var(--color-text-secondary)]">
                {plan.desc}
              </p>

              {/* Features */}
              <ul className="flex flex-col gap-[var(--space-10)] m-0 p-0 list-none flex-1">
                {plan.features.map((f) => (
                  <li
                    key={f}
                    className="flex items-start gap-[var(--space-10)] text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-secondary)]"
                  >
                    <span
                      aria-hidden
                      className="flex items-center justify-center w-[20px] h-[20px] rounded-full text-[12px] leading-[1] shrink-0"
                      style={{
                        background:
                          'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.12)',
                        color: 'rgb(var(--accent-r), var(--accent-g), var(--accent-b))',
                      }}
                    >
                      ✓
                    </span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <button
                type="button"
                onClick={() => handleBuy(plan.packQty)}
                disabled={loading === plan.packQty}
                className={`w-full px-[var(--space-20)] py-[var(--space-12)] text-[15px] tablet:text-[16px] leading-[22px] tablet:leading-[24px] rounded-[var(--radius-12)] font-medium ${
                  plan.highlighted ? 'glass-btn-primary' : 'glass-btn-secondary text-[var(--color-brand-primary)]'
                }`}
              >
                {loading === plan.packQty ? 'Загрузка…' : plan.ctaLabel}
              </button>
            </article>
          ))}

          {/* Corporate / B2B card — другая семантика, без покупки */}
          <article
            className="snap-center gradient-border-card glass-card flex flex-col gap-[var(--space-20)] tablet:gap-[var(--space-24)] p-[var(--space-20)] tablet:p-[var(--space-28)] w-[calc(100vw-56px)] tablet:w-auto min-w-0 tablet:flex-[0.95] h-auto tablet:min-h-[520px] rounded-[var(--radius-16)]"
          >
            <div className="flex items-center justify-between gap-[var(--space-12)]">
              <span className="text-[20px] tablet:text-[22px] leading-[28px] tablet:leading-[30px] font-semibold text-[var(--color-text-primary)]">
                Корпоративный тариф
              </span>
              <span
                className="px-[var(--space-8)] py-[2px] text-[12px] font-medium leading-[16px] rounded-full"
                style={{
                  background:
                    'rgba(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b), 0.12)',
                  border:
                    '1px solid rgba(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b), 0.30)',
                  color: 'var(--color-text-primary)',
                }}
              >
                B2B
              </span>
            </div>

            <div className="flex flex-col gap-[var(--space-8)]">
              <span className="text-[28px] tablet:text-[32px] leading-[1.1] font-bold text-[var(--color-text-primary)]">
                По объёму
              </span>
              <span className="text-[14px] leading-[20px] text-[var(--color-text-muted)]">
                Договор, счёт, безналичный расчёт
              </span>
            </div>

            <p className="text-[14px] tablet:text-[15px] leading-[20px] tablet:leading-[22px] text-[var(--color-text-secondary)]">
              AI-генерация в брендовом фотобанке, маркетплейсе или мобильном приложении. Подключаем по API под ваш объём.
            </p>

            <ul className="flex flex-col gap-[var(--space-10)] m-0 p-0 list-none flex-1">
              {CORPORATE_FEATURES.map((f) => (
                <li
                  key={f}
                  className="flex items-start gap-[var(--space-10)] text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-secondary)]"
                >
                  <span>{f}</span>
                </li>
              ))}
            </ul>

            <button
              type="button"
              onClick={handleCorporate}
              className="glass-btn-secondary w-full px-[var(--space-20)] py-[var(--space-12)] text-[15px] tablet:text-[16px] leading-[22px] tablet:leading-[24px] rounded-[var(--radius-12)] font-medium text-[var(--color-brand-primary)]"
            >
              Узнать про API
            </button>
          </article>
        </div>
      </div>

      <p className="text-center text-[13px] tablet:text-[14px] leading-[20px] text-[var(--color-text-muted)] max-w-[600px]">
        Все пакеты идут на один баланс — фото можно потратить на любую категорию.
      </p>
    </section>
  );
}
