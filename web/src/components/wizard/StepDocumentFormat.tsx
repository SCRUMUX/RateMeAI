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
    <div className="flex flex-col h-full w-full max-w-[800px] mx-auto">
      <div className="shrink-0 flex flex-col gap-[var(--space-4)] text-center pb-[var(--space-12)]">
        <h2 className="text-[20px] tablet:text-[24px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Выберите формат
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)]">
          Фото будет оптимизировано под требования формата
        </p>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-[var(--space-8)]">
        {formats.map((fmt) => {
          const isActive = selectedKey === fmt.key;
          return (
            <button
              key={fmt.key}
              type="button"
              onClick={() => handleSelect(fmt.key)}
              className={`gradient-border-item flex items-center w-full px-[var(--space-16)] py-[var(--space-8)] gap-[var(--space-4)] min-h-[44px] cursor-pointer rounded-[var(--radius-12)] transition-all text-left ${
                isActive ? 'glass-row-active' : 'glass-row'
              }`}
              style={{
                '--gb-color': isActive
                  ? 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.30)'
                  : 'rgba(255, 255, 255, 0.10)',
              } as React.CSSProperties}
            >
              <div className="flex items-center justify-center w-5 h-5 shrink-0 text-[18px] leading-none">
                {fmt.icon}
              </div>
              <div className="flex flex-col flex-1 min-w-0 gap-[2px]">
                <span className="text-[15px] leading-[20px] text-[#E6EEF8] font-medium truncate">
                  {fmt.name}
                </span>
                <span className="text-[11px] leading-[14px] text-[var(--color-text-muted)] truncate">
                  {fmt.desc}{fmt.usage ? ` · ${fmt.usage}` : ''}
                </span>
              </div>
              {isActive && (
                <div className="shrink-0 flex items-center justify-center w-5 h-5">
                  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                    <path d="M5 9.5L7.5 12L13 6" stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
              )}
            </button>
          );
        })}
      </div>

      <div className="shrink-0 pt-[var(--space-12)]">
        <button
          onClick={handleSelectAndNext}
          className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-pill)] font-medium"
        >
          Далее
        </button>
      </div>
    </div>
  );
}
