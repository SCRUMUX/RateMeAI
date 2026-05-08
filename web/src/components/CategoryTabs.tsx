import { useTranslation } from 'react-i18next';
import { CATEGORIES, COMING_SOON_CATEGORIES, type CategoryId } from '../data/styles';

interface CategoryTabsProps {
  active: CategoryId;
  onChange: (id: CategoryId) => void;
  /**
   * 1.50.0: на лендинге временно скрываем coming-soon направления
   * (модель/бренд/мемы) — пока фронт-данные не готовы. В wizard
   * флаг по умолчанию false, там «скоро» работает как раньше.
   */
  hideComingSoon?: boolean;
}

/**
 * 1.50.0: убрана внешняя плашка `gradient-border-card glass` —
 * кнопки направлений теперь рендерятся прямо на фоне страницы.
 * Плашка визуально дублировала плашки внутри Simulation и делала
 * блок «громоздким».
 */
export default function CategoryTabs({ active, onChange, hideComingSoon = false }: CategoryTabsProps) {
  const { t } = useTranslation('landing');
  const visible = hideComingSoon
    ? CATEGORIES.filter((cat) => !COMING_SOON_CATEGORIES.includes(cat.id))
    : CATEGORIES;
  const cols = visible.length <= 3
    ? 'grid-cols-3'
    : visible.length === 4
      ? 'grid-cols-2 tablet:grid-cols-4'
      : 'grid-cols-3';
  return (
    <div className={`grid ${cols} gap-[var(--space-8)] tablet:gap-[var(--space-12)] w-full max-w-[720px]`}>
      {visible.map((cat) => {
        const isDisabled = !hideComingSoon && COMING_SOON_CATEGORIES.includes(cat.id);
        return (
          <button key={cat.id}
            disabled={isDisabled}
            onClick={() => !isDisabled && onChange(cat.id)}
            className={`relative flex items-center justify-center gap-[var(--space-6)] tablet:gap-[var(--space-8)] px-[var(--space-12)] tablet:px-[var(--space-16)] py-[var(--space-10)] tablet:py-[var(--space-12)] min-h-[44px] tablet:min-h-[48px] rounded-[var(--radius-pill)] text-[13px] tablet:text-[15px] leading-[18px] tablet:leading-[20px] font-medium transition-all whitespace-nowrap ${
              isDisabled
                ? 'opacity-40 cursor-not-allowed text-[var(--color-text-muted)]'
                : active === cat.id
                  ? 'glass-tab-active'
                  : 'glass-btn-ghost text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
            }`}
          >
            <span className="text-[15px] tablet:text-[17px]">{cat.icon}</span>
            {cat.label}
            {isDisabled && <span className="text-[9px] tablet:text-[10px] leading-none opacity-70 absolute -top-[2px] -right-[2px]">{t('categoryTabs.comingSoon')}</span>}
          </button>
        );
      })}
    </div>
  );
}
