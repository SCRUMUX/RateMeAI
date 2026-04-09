import { useState } from 'react';
import { CoinIcon, ImageIcon } from '@ai-ds/core/icons';
import { useApp } from '../context/AppContext';
import { createPayment, ApiError } from '../lib/api';

const PLANS = [
  { title: 'Попробовать', price: '59 рублей', photos: '1 фото', packQty: 1, desc: 'Посмотри, как AI улучшит твоё фото за секунды. Идеально, чтобы оценить результат перед полной прокачкой.', highlighted: false, badge: null, savingBadge: null },
  { title: 'Обновить фото', price: '199 рублей', photos: '5 фото', packQty: 5, desc: 'Освежи свои лучшие снимки и выбери идеальный вариант для соцсетей или профиля.', highlighted: false, badge: null, savingBadge: null },
  { title: 'Прокачать образ', price: '499 рублей', photos: '15 фото', packQty: 15, desc: 'Полная прокачка твоего образа под разные ситуации: соцсети, знакомства, работа. Найди фото, которое реально работает.', highlighted: true, badge: 'BEST', savingBadge: 'Экономия 40%' },
  { title: 'Полная трансформация', price: '899 рублей', photos: '30 фото', packQty: 30, desc: 'Максимум вариантов и стилей. Подходит, если хочешь полностью обновить свой визуальный образ и выделяться в любой ситуации.', highlighted: false, badge: null, savingBadge: null },
];

export default function Pricing() {
  const { session } = useApp();
  const [loading, setLoading] = useState<number | null>(null);

  async function handleBuy(packQty: number) {
    if (!session) {
      document.getElementById('app')?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    setLoading(packQty);
    try {
      const res = await createPayment(packQty);
      window.location.href = res.confirmation_url;
    } catch (e) {
      alert(e instanceof ApiError ? 'Ошибка создания платежа' : 'Ошибка');
      setLoading(null);
    }
  }

  return (
    <section id="тарифы" className="relative z-[2] flex flex-col items-center gap-[var(--space-96)] px-[var(--space-24)] py-[120px]"
      style={{ minHeight: '100vh' }}
    >
      {/* Heading */}
      <div className="relative flex flex-col items-center gap-[var(--space-12)] text-center">
        <h2 className="text-[64px] font-semibold leading-[1] text-[#E6EEF8]">Тарифы</h2>
        <h2 className="text-[64px] font-semibold leading-[1]"
          style={{ background: 'linear-gradient(105deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
        >
          — попробуй бесплатно
        </h2>
        <p className="text-[20px] leading-[28px] text-[var(--color-text-secondary)]">И продолжай если понравится</p>
        <button
          onClick={() => document.getElementById('app')?.scrollIntoView({ behavior: 'smooth' })}
          className="glass-btn-secondary mt-[var(--space-8)] px-[var(--space-20)] py-[var(--space-10)] text-[16px] leading-[24px] text-[var(--color-brand-primary)] rounded-[var(--radius-12)]"
        >
          Попробовать бесплатное улучшение
        </button>
      </div>

      {/* Cards */}
      <div className="relative flex items-start justify-between w-full max-w-[1386px] gap-[10px]">
        {PLANS.map((plan, i) => (
          <div key={i}
            className={`gradient-border-card flex flex-col gap-[var(--space-32)] p-[var(--space-32)] h-[480px] rounded-[var(--radius-12)] ${
              plan.highlighted
                ? 'glass-card-highlight flex-[1.15]'
                : 'glass-card flex-1'
            }`}
          >
            <div className="flex items-center gap-[var(--space-6)] px-[var(--space-8)] py-[var(--space-4)]">
              <span className="text-style-h1 text-[#E6EEF8] whitespace-nowrap">{plan.title}</span>
              {plan.badge && (
                <span className="glass-badge-info px-[var(--space-6)] py-[2px] text-[12px] font-medium leading-[16px] text-[#E6EEF8] rounded-full">{plan.badge}</span>
              )}
            </div>

            <div className="flex items-center gap-[var(--space-8)] px-[var(--space-8)] py-[var(--space-4)]">
              <CoinIcon size={24} className={plan.highlighted ? 'text-[var(--color-brand-primary)]' : 'text-[var(--color-text-muted)]'} />
              <span className={`text-[24px] leading-[32px] font-medium ${plan.highlighted ? 'text-[var(--color-brand-primary)]' : 'text-[#E6EEF8]'}`}>{plan.price}</span>
            </div>

            <div className="flex items-center gap-[var(--space-8)] px-[var(--space-4)] py-[2px]">
              <ImageIcon size={16} className="text-[var(--color-text-muted)]" />
              <span className="text-[16px] leading-[24px] text-[var(--color-text-secondary)]">{plan.photos}</span>
              {plan.savingBadge && (
                <span className="glass-badge-danger px-[var(--space-6)] py-[2px] text-[12px] font-medium leading-[16px] text-[#E6EEF8] rounded-full">{plan.savingBadge}</span>
              )}
            </div>

            <p className="text-[16px] leading-[24px] text-[var(--color-text-secondary)] flex-1">{plan.desc}</p>

            <button
              onClick={() => handleBuy(plan.packQty)}
              disabled={loading === plan.packQty}
              className={`w-full px-[var(--space-20)] py-[var(--space-10)] text-[16px] leading-[24px] rounded-[var(--radius-12)] ${
                plan.highlighted
                  ? 'glass-btn-primary'
                  : i === PLANS.length - 1
                    ? 'glass-btn-secondary font-medium text-[var(--color-brand-primary)]'
                    : 'glass-btn-ghost font-medium'
              }`}
            >
              {loading === plan.packQty ? 'Загрузка...' : 'Выбрать'}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
