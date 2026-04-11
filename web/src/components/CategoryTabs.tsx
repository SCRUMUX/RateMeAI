import { CATEGORIES, type CategoryId } from '../data/styles';

interface CategoryTabsProps {
  active: CategoryId;
  onChange: (id: CategoryId) => void;
}

export default function CategoryTabs({ active, onChange }: CategoryTabsProps) {
  return (
    <div className="w-full overflow-x-auto scrollbar-hide tablet:w-auto tablet:overflow-x-visible">
      <div className="gradient-border-card glass flex items-center gap-[var(--space-8)] tablet:gap-[19px] rounded-[var(--radius-12)] px-[var(--space-8)] tablet:px-[var(--space-12)] py-[var(--space-8)] w-max tablet:w-auto mx-auto">
        {CATEGORIES.map((cat) => (
          <button key={cat.id}
            onClick={() => onChange(cat.id)}
            className={`flex items-center gap-[var(--space-6)] tablet:gap-[var(--space-8)] px-[var(--space-12)] tablet:px-[var(--space-20)] py-[var(--space-8)] tablet:py-[var(--space-10)] min-h-[40px] tablet:min-h-[44px] rounded-[var(--radius-12)] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] font-medium transition-all whitespace-nowrap ${
              active === cat.id
                ? 'glass-tab-active'
                : 'glass-btn-ghost text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
            }`}
          >
            <span>{cat.icon}</span>
            {cat.label}
          </button>
        ))}
      </div>
    </div>
  );
}
