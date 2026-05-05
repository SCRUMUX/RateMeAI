export interface HowItWorksStep {
  num: string;
  title: string;
  desc: string;
}

export interface HowItWorksProps {
  /** Optional override for the 4-step list. Defaults to the home flow. */
  steps?: HowItWorksStep[];
  /** Optional heading shown above the cards. */
  title?: string;
}

const DEFAULT_STEPS: HowItWorksStep[] = [
  { num: '1', title: 'Загрузи фото', desc: 'Крупный анфас, ≥400×400, один человек в кадре. Фото без лица и размытые не обрабатываются.' },
  { num: '2', title: 'Выбери категорию', desc: 'Экспериментируй с образами! 3 категории и более 100 стилей в каждой' },
  { num: '3', title: 'Получи результат', desc: 'Адаптированное фото и оценка восприятия от 0 до 10. Всё объяснено.' },
  { num: '4', title: 'Прокачивай образ', desc: 'Не понравился результат — генерируй снова. Скор растёт с каждой итерацией.' },
];

/**
 * "How it works" block. Reused on the home landing and on every
 * scenario landing (Dating, Resume, Documents) — the visual shell is
 * always identical, only the four step labels differ. Cards stretch
 * to the same height (CSS grid + flex-grow on the description) so
 * the row stays symmetrical even when titles wrap to different line
 * counts between cards.
 */
export default function HowItWorks({ steps = DEFAULT_STEPS, title }: HowItWorksProps) {
  return (
    <section className="relative z-[2] w-full">
      <div className="howworks-wrapper relative w-full glass-divider">
        <div className="howworks-gradient-backdrop" />
        <div className="relative flex flex-col items-center gap-[var(--space-24)] tablet:gap-[var(--space-40)] w-full max-w-[1200px] mx-auto px-[var(--space-16)] tablet:px-[var(--space-32)] py-[var(--space-32)] tablet:py-[var(--space-64)]">
          {title && (
            <h2 className="reveal landing-h2 text-[var(--color-text-primary)] text-center">{title}</h2>
          )}
          <div className="reveal-stagger howworks-grid w-full">
            {steps.map((s) => (
              <article
                key={s.num}
                className="howworks-card gradient-border-card glass-card rounded-[var(--radius-12)]"
              >
                <div className="howworks-card-num">
                  <span className="text-[16px] leading-[24px] text-[var(--color-brand-primary)]">{s.num}</span>
                </div>
                <h3 className="howworks-card-title text-[var(--color-text-primary)]">
                  {s.title}
                </h3>
                <p className="howworks-card-desc landing-body">
                  {s.desc}
                </p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
