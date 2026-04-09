const STEPS = [
  { num: '1', title: 'Загрузи фото', desc: 'С телефон или компьютера. Чем лучше четче фото, тем лучше результат.' },
  { num: '2', title: 'Выбери категорию', desc: 'Экспериментируй с образами! 3 категории и более 100 стилей в каждой' },
  { num: '3', title: 'Получи результат', desc: 'Адаптированное фото и оценка восприятия от 0 до 10. Всё объяснено.' },
  { num: '4', title: 'Прокачивай образ', desc: 'Не понравился результат — генерируй снова. Скор растёт с каждой итерацией.' },
];

export default function HowItWorks() {
  return (
    <section className="relative z-[2] w-full">
      <div className="howworks-wrapper relative w-full glass-divider">
        <div className="howworks-gradient-backdrop" />
        <div className="relative flex items-start justify-between w-full max-w-[1200px] mx-auto gap-[var(--space-24)] p-[var(--space-24)]">
          {STEPS.map((s) => (
            <div key={s.num} className="gradient-border-card glass-card flex flex-col items-center gap-[var(--space-12)] p-[var(--space-12)] flex-1 rounded-[var(--radius-12)]">
              <div className="flex items-center justify-center w-[44px] h-[44px] rounded-full"
                style={{
                  background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.06)',
                  border: '1px solid rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.25)',
                  boxShadow: '0 0 12px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.08)',
                }}
              >
                <span className="text-[16px] leading-[24px] text-[var(--color-brand-primary)]">{s.num}</span>
              </div>
              <h3 className="text-style-h1 text-[#E6EEF8] text-center whitespace-nowrap">
                {s.title}
              </h3>
              <p className="text-[16px] leading-[24px] text-[var(--color-text-secondary)] text-center">
                {s.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
