import { CATEGORIES, type CategoryId } from '../data/styles';

interface CategoryTabsProps {
  active: CategoryId;
  onChange: (id: CategoryId) => void;
}

export default function CategoryTabs({ active, onChange }: CategoryTabsProps) {
  return (
    <div className="gradient-border-card glass rounded-[var(--radius-12)] px-[var(--space-6)] tablet:px-[var(--space-10)] py-[var(--space-6)] tablet:py-[var(--space-8)]">
      <div className="grid grid-cols-3 gap-[var(--space-6)] tablet:gap-[var(--space-8)]">
        {CATEGORIES.map((cat) => (
          <button key={cat.id}
            onClick={() => onChange(cat.id)}
            className={`flex items-center justify-center gap-[var(--space-4)] tablet:gap-[var(--space-6)] px-[var(--space-6)] tablet:px-[var(--space-10)] py-[var(--space-6)] tablet:py-[var(--space-8)] min-h-[36px] tablet:min-h-[40px] rounded-[var(--radius-8)] text-[12px] tablet:text-[14px] leading-[16px] tablet:leading-[20px] font-medium transition-all whitespace-nowrap ${
              active === cat.id
                ? 'glass-tab-active'
                : 'glass-btn-ghost text-[var(--color-text-secondary)] hover:text-[#E6EEF8]'
            }`}
          >
            <span className="text-[14px] tablet:text-[16px]">{cat.icon}</span>
            {cat.label}
          </button>
        ))}
      </div>
    </div>
  );
}
