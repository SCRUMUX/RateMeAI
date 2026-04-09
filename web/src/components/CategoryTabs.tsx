import { CATEGORIES, type CategoryId } from '../data/styles';

interface CategoryTabsProps {
  active: CategoryId;
  onChange: (id: CategoryId) => void;
}

export default function CategoryTabs({ active, onChange }: CategoryTabsProps) {
  return (
    <div className="gradient-border-card glass flex items-center gap-[19px] rounded-[var(--radius-12)] px-[var(--space-12)] py-[var(--space-8)]">
      {CATEGORIES.map((cat) => (
        <button key={cat.id}
          onClick={() => onChange(cat.id)}
          className={`flex items-center gap-[var(--space-8)] px-[var(--space-20)] py-[var(--space-10)] min-h-[44px] rounded-[var(--radius-12)] text-[16px] leading-[24px] font-medium transition-all ${
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
  );
}
