import { useApp } from '../../context/AppContext';
import { isDocumentFormatItem, type DocumentFormatItem } from '../../scenarios/extraStyles';

interface Props {
  onNext: () => void;
}

export default function StepDocumentFormat({ onNext }: Props) {
  const app = useApp();
  const formats = app.effectiveStyleList.filter(isDocumentFormatItem) as DocumentFormatItem[];
  const selectedKey = app.selectedStyleKey || formats[0]?.key || '';

  function handleSelect(key: string) {
    app.setSelectedStyleKey(key);
  }

  function handleSelectAndNext() {
    const effective = app.selectedStyleKey || formats[0]?.key || '';
    if (!app.selectedStyleKey && effective) {
      app.setSelectedStyleKey(effective);
    }
    onNext();
  }

  return (
    <div className="flex flex-col h-full max-w-[800px] mx-auto">
      <div className="shrink-0 flex flex-col gap-[var(--space-6)] text-center pb-[var(--space-16)]">
        <h2 className="text-[24px] tablet:text-[28px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Выберите формат документа
        </h2>
        <p className="text-[13px] tablet:text-[14px] leading-[18px] tablet:leading-[20px] text-[var(--color-text-secondary)]">
          Фото будет оптимизировано под требования выбранного формата
        </p>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-[var(--space-10)]">
        {formats.map((fmt) => {
          const isActive = selectedKey === fmt.key;
          return (
            <div
              key={fmt.key}
              onClick={() => handleSelect(fmt.key)}
              className={`gradient-border-item flex items-start w-full px-[var(--space-16)] py-[var(--space-12)] gap-[var(--space-12)] rounded-[var(--radius-12)] transition-all cursor-pointer ${
                isActive ? 'glass-row-active' : 'glass-row'
              }`}
              style={{
                '--gb-color': isActive
                  ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)'
                  : 'rgba(255, 255, 255, 0.10)',
              } as React.CSSProperties}
            >
              <div className="flex items-center justify-center w-8 h-8 shrink-0 text-[24px] leading-none mt-[2px]">
                {fmt.icon}
              </div>
              <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                <span className="text-[16px] leading-[24px] text-[#E6EEF8] font-medium">
                  {fmt.name}
                </span>
                <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)]">
                  {fmt.desc}
                </span>
                <span className="text-[11px] leading-[14px] text-[var(--color-text-secondary)] mt-[2px]">
                  {fmt.usage}
                </span>
              </div>
              {isActive && (
                <div className="shrink-0 flex items-center justify-center w-6 h-6 mt-[4px]">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M5 9.5L7.5 12L13 6" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="shrink-0 pt-[var(--space-16)]">
        <button
          onClick={handleSelectAndNext}
          className="glass-btn-primary w-full py-[var(--space-10)] text-[14px] leading-[20px] rounded-[var(--radius-pill)] font-medium"
        >
          Генерировать
        </button>
      </div>
    </div>
  );
}
