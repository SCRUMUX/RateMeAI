import { CATEGORIES, COMING_SOON_CATEGORIES, type CategoryId } from '../data/styles';

interface CategoryTabsProps {
  active: CategoryId;
  onChange: (id: CategoryId) => void;
}

export default function CategoryTabs({ active, onChange }: CategoryTabsProps) {
  return (
    <div className="gradient-border-card glass rounded-[var(--radius-12)] px-[var(--space-6)] tablet:px-[var(--space-10)] py-[var(--space-6)] tablet:py-[var(--space-8)]">
      <div className="grid grid-cols-3 gap-[var(--space-6)] tablet:gap-[var(--space-8)]">
        {CATEGORIES.map((cat) => {
          const isDisabled = COMING_SOON_CATEGORIES.includes(cat.id);
          return (
            <button key={cat.id}
              disabled={isDisabled}
              onClick={() => !isDisabled && onChange(cat.id)}
              className={`relative flex items-center justify-center gap-[var(--space-4)] tablet:gap-[var(--space-6)] px-[var(--space-6)] tablet:px-[var(--space-10)] py-[var(--space-6)] tablet:py-[var(--space-8)] min-h-[36px] tablet:min-h-[40px] rounded-[var(--radius-8)] text-[12px] tablet:text-[14px] leading-[16px] tablet:leading-[20px] font-medium transition-all whitespace-nowrap ${
                isDisabled
                  ? 'opacity-40 cursor-not-allowed text-[var(--color-text-muted)]'
                  : active === cat.id
                    ? 'glass-tab-active'
                    : 'glass-btn-ghost text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
              }`}
            >
              <span className="text-[14px] tablet:text-[16px]">{cat.icon}</span>
              {cat.label}
              {isDisabled && <span className="text-[9px] tablet:text-[10px] leading-none opacity-70 absolute -top-[2px] -right-[2px]">скоро</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
