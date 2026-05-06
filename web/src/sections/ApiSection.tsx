import { useState } from 'react';
import { findBlock, type LandingPage } from '../lib/landing-cms';

/**
 * 1.50.6 — секция «API» под блоком «Тарифы» на главной.
 *
 * Повторяет UX-паттерн «Симулятора»: справа — список плашек
 * (выбор сценария интеграции), слева — описание выбранного API
 * с маркетинговыми преимуществами и общая CTA-кнопка.
 *
 * Контент по умолчанию задан в `DEFAULT_OPTIONS`. CMS-блок `api`
 * опционально переопределяет title/subtitle и текст CTA — сами
 * варианты остаются захардкожены клиентом, чтобы не зависеть от
 * наполнения CMS.
 *
 * CTA «Написать по сотрудничеству» открывает Telegram автора
 * (`https://t.me/scrumux`) в новой вкладке.
 */

const COOPERATION_TG_URL = 'https://t.me/scrumux';

interface ApiOption {
  key: string;
  icon: string;
  name: string;
  tagline: string;
  description: string;
  benefits: string[];
}

const DEFAULT_OPTIONS: ApiOption[] = [
  {
    key: 'dating',
    icon: '💘',
    name: 'API для сайтов знакомств',
    tagline: 'Анкеты, на которые отвечают',
    description:
      'Подключаем фото-улучшение прямо в onboarding и редактор анкеты. Сервис адаптирует свет, фон, мимику и кадрирование, не теряя сходство с человеком — пользователь получает несколько сильных вариантов вместо одного среднего.',
    benefits: [
      'Рост CTR анкет и количества мэтчей за счёт фотографий, прошедших проверку фотореализма',
      'Готовый сценарий «загрузил → выбрал стиль → опубликовал» — без отдельных приложений и фотостудий',
      'Гибкая модерация: автоматический отсев нечётких, групповых и неподходящих кадров',
    ],
  },
  {
    key: 'hr',
    icon: '💼',
    name: 'API для кадровых агентств',
    tagline: 'Корпоративные портреты в один клик',
    description:
      'Для HR-платформ, ATS и job-board: единый стандарт фотографий в анкетах кандидатов. Вместо случайных селфи — спокойный фон, уверенная мимика и аккуратный кадр под бизнес-сценарий, без выезда соискателя в фотостудию.',
    benefits: [
      'Единый визуальный стандарт кандидатов — сильнее впечатление работодателя на первом скрининге',
      'Сокращение цикла найма: нет промежуточного шага «принесите нормальное фото»',
      'Подходит для LinkedIn, hh.ru, корпоративных карьерных порталов и внутренних HR-систем',
    ],
  },
  {
    key: 'studio',
    icon: '📸',
    name: 'API для фотостудий',
    tagline: 'Расширьте линейку онлайн',
    description:
      'Достроим продуктовую линейку студии онлайн-сценариями: фото на документы, лайфстайл-портреты, фото для соцсетей и резюме. Каждый формат с собственными размерами, фоном и стилистикой. Возможно white-label под бренд студии.',
    benefits: [
      'Новый поток заказов 24/7 без расширения штата фотографов и ретушёров',
      'Готовый фотобанк под клиента — пакеты, подписки, корпоративные тарифы',
      'White-label интеграция: ваш домен, ваш бренд, ваша касса',
    ],
  },
  {
    key: 'custom',
    icon: '⚙️',
    name: 'API для кастомных задач',
    tagline: 'Под ваш сценарий и бренд',
    description:
      'Подключаем под нестандартные сценарии: маркетплейсы аватаров, бьюти-приложения, образовательные платформы, фотобанки. Подбираем стилистику, форматы и алгоритм проверки под задачу. По объёму возможна тренировка кастомной модели.',
    benefits: [
      'Контракт и стоимость по объёму — без переплат за «коробочный» тариф',
      'Выделенный SLA, прямая поддержка интеграции и помощь на стороне разработки',
      'Возможна донастройка модели под фирменную стилистику и редполитику бренда',
    ],
  },
];

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

export default function ApiSection({ cmsPage }: { cmsPage?: LandingPage | null }) {
  const block = findBlock(cmsPage ?? undefined, 'api');
  const data = (block?.data ?? {}) as Record<string, unknown>;

  const title = asString(data.title, 'API для интеграций');
  const subtitle = asString(
    data.subtitle,
    'Подключите фото-улучшение и анализ восприятия в свой продукт. Выберите сценарий — мы покажем, что и как умеем делать.',
  );
  const ctaLabel = asString(data.primaryCtaLabel, 'Написать по сотрудничеству');

  const [activeIdx, setActiveIdx] = useState(0);
  const active = DEFAULT_OPTIONS[activeIdx];

  return (
    <section
      id="api"
      className="relative z-[2] flex flex-col items-center gap-[var(--space-40)] tablet:gap-[var(--space-64)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-section-py"
    >
      {/* Heading */}
      <div className="reveal relative flex flex-col items-center gap-[var(--space-12)] text-center max-w-[760px]">
        <h2 className="landing-h2 text-[var(--color-text-primary)]">{title}</h2>
        <p className="landing-lead">{subtitle}</p>
      </div>

      {/* Two-column layout: на десктопе слева — выбор сценария API,
          справа — описание + преимущества + CTA. На mobile колонки
          складываются: сначала список, потом описание — пользователь
          сразу видит, что переключается, а не пролистывает описание
          раньше списка. */}
      <div className="relative flex flex-col desktop:flex-row items-stretch desktop:items-start desktop:justify-between w-full max-w-[1200px] gap-[var(--space-24)] desktop:gap-[70px]">
        {/* Right (на десктопе): описание + преимущества */}
        <div className="flex flex-col w-full desktop:flex-1 desktop:max-w-[560px] order-last desktop:order-last">
          <div className="gradient-border-card glass-card flex flex-col gap-[var(--space-20)] p-[var(--space-24)] tablet:p-[var(--space-32)] rounded-[var(--radius-12)] h-full">
            <div className="flex items-center gap-[var(--space-12)]">
              <span
                aria-hidden
                className="flex items-center justify-center w-[48px] h-[48px] rounded-[var(--radius-12)] text-[28px]"
                style={{
                  background:
                    'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.08)',
                  border:
                    '1px solid rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.18)',
                }}
              >
                {active.icon}
              </span>
              <div className="flex flex-col gap-[var(--space-2)]">
                <span className="text-[20px] tablet:text-[22px] leading-[28px] tablet:leading-[30px] font-semibold text-[var(--color-text-primary)]">
                  {active.name}
                </span>
                <span className="text-[13px] leading-[18px] uppercase tracking-[0.08em] text-[var(--color-brand-primary)]">
                  {active.tagline}
                </span>
              </div>
            </div>

            <p className="landing-body text-[var(--color-text-secondary)]">
              {active.description}
            </p>

            <ul className="flex flex-col gap-[var(--space-12)] m-0 p-0 list-none">
              {active.benefits.map((b, i) => (
                <li
                  key={i}
                  className="flex items-start gap-[var(--space-12)] text-[14px] tablet:text-[15px] leading-[20px] tablet:leading-[22px] text-[var(--color-text-secondary)]"
                >
                  <span
                    aria-hidden
                    className="flex items-center justify-center w-[20px] h-[20px] mt-[2px] rounded-full text-[12px] leading-[1] shrink-0"
                    style={{
                      background:
                        'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.12)',
                      color: 'rgb(var(--accent-r), var(--accent-g), var(--accent-b))',
                    }}
                  >
                    ✓
                  </span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>

            <a
              href={COOPERATION_TG_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="glass-btn-primary inline-flex items-center justify-center w-full px-[var(--space-24)] py-[var(--space-12)] text-[15px] tablet:text-[16px] leading-[22px] tablet:leading-[24px] rounded-[var(--radius-12)] font-medium no-underline mt-[var(--space-4)]"
            >
              {ctaLabel}
            </a>
          </div>
        </div>

        {/* Left (на десктопе): список плашек API */}
        <div className="flex flex-col gap-[var(--space-20)] w-full desktop:max-w-[480px] order-first desktop:order-first">
          {DEFAULT_OPTIONS.map((option, i) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setActiveIdx(i)}
              className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-12)] gap-[var(--space-12)] cursor-pointer rounded-[var(--radius-12)] transition-all text-left ${
                activeIdx === i ? 'glass-row-active' : 'glass-row'
              }`}
              style={
                {
                  '--gb-color':
                    activeIdx === i
                      ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)'
                      : 'var(--glass-border-hover)',
                } as React.CSSProperties
              }
              aria-pressed={activeIdx === i}
            >
              <span
                aria-hidden
                className="flex items-center justify-center w-9 h-9 rounded-[var(--radius-12)] shrink-0 text-[20px] leading-none"
                style={{
                  background:
                    activeIdx === i
                      ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.10)'
                      : 'transparent',
                }}
              >
                {option.icon}
              </span>
              <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                <span className="text-[16px] leading-[22px] text-[var(--color-text-primary)] font-medium truncate">
                  {option.name}
                </span>
                <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] truncate">
                  {option.tagline}
                </span>
              </div>
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                aria-hidden
                className={`shrink-0 transition-transform ${activeIdx === i ? 'translate-x-0' : '-translate-x-[2px] opacity-60'}`}
                style={{ color: activeIdx === i ? 'rgb(var(--accent-r), var(--accent-g), var(--accent-b))' : 'var(--color-text-muted)' }}
              >
                <path
                  d="M6 4l4 4-4 4"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
