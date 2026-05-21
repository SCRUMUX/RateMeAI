/**
 * Продуктовый tier-каталог. Единая модель в пайплайне —
 * `gpt_image_2`; продуктовый выбор сводится к «Стандарт / Премиум».
 *
 *   * «Стандарт»  → `image_model=gpt_image_2`, `image_quality=medium`,
 *                   без refiner-а. ≈ $0.06/img. 1 кредит.
 *   * «Премиум»   → тот же базовый рендер плюс Clarity Upscaler
 *                   post-pass с `upscale_factor=2` — реальное
 *                   повышение разрешения (≈$0.10/img общая стоимость
 *                   на стороне FAL). 2 кредита; если refiner упал,
 *                   1 кредит автоматически возвращается.
 *
 * Бэк (`src/services/analysis_request.py::apply_tier_context_fields`)
 * на любом tier'е жёстко пинит `image_model=gpt_image_2`, поэтому
 * клиентский `imageModel` остаётся только лейблом совместимости
 * со старыми SPA-бандлами.
 */
import type { AbImageModel, AbImageQuality, AbProductTier } from '../lib/api';
import i18next from '../lib/i18n';

export interface AbModelMeta {
  /** Внутренний идентификатор tier'а (тот же, что и `AbProductTier`). */
  key: AbProductTier;
  /** Какую модель посылать на бэк. Всегда `gpt_image_2`. */
  imageModel: AbImageModel;
  label: string;
  short: string;
  description: string;
  /** Сколько кредитов пользователь видит в UI за одну генерацию. */
  creditCost: number;
  /** USD per image, indexed by quality tier — используется только в телеметрии/бэке. */
  cost: Record<AbImageQuality, number>;
}

interface AbModelDef {
  key: AbProductTier;
  imageModel: AbImageModel;
  /** RU-fallback используется, если ключа в catalog.json нет. */
  label: string;
  short: string;
  description: string;
  creditCost: number;
  cost: Record<AbImageQuality, number>;
}

const AB_MODEL_DEFS: AbModelDef[] = [
  {
    key: 'standard',
    imageModel: 'gpt_image_2',
    label: 'Стандарт',
    short: 'Сбалансированный рендер',
    description:
      'Стандартный рендер на GPT Image 2 (medium quality). Хорошая ' +
      'адгезия промпта и стабильная передача лица. Подходит для ' +
      'большинства сценариев.',
    creditCost: 1,
    cost: { low: 0.02, medium: 0.06, high: 0.12 },
  },
  {
    key: 'premium',
    imageModel: 'gpt_image_2',
    label: 'Премиум',
    short: 'Выше разрешение и больше деталей',
    description:
      'Тот же базовый рендер, но с увеличением разрешения в 2× и ' +
      'дополнительной полировкой деталей: чётче текстура кожи, ' +
      'волосы и фон. Композиция и идентичность лица сохраняются.',
    creditCost: 2,
    cost: { low: 0.08, medium: 0.10, high: 0.10 },
  },
];

/**
 * AB_MODELS is a Proxy-backed array — each access to `label`/`short`/
 * `description` lazily reads from i18next so the EN build renders
 * English copy without touching every consumer.
 */
export const AB_MODELS: AbModelMeta[] = AB_MODEL_DEFS.map((def) =>
  new Proxy(def, {
    get(target, prop, receiver) {
      if (prop === 'label') {
        return i18next.t(`catalog:abModels.${target.key}.label`, target.label) || target.label;
      }
      if (prop === 'short') {
        return i18next.t(`catalog:abModels.${target.key}.short`, target.short) || target.short;
      }
      if (prop === 'description') {
        return (
          i18next.t(`catalog:abModels.${target.key}.description`, target.description)
          || target.description
        );
      }
      return Reflect.get(target, prop, receiver);
    },
  }) as AbModelMeta,
);

export function getAbModelLabel(key: AbProductTier): string {
  const def = AB_MODEL_DEFS.find((m) => m.key === key);
  const fallback = def?.label ?? key;
  return i18next.t(`catalog:abModels.${key}.label`, fallback) || fallback;
}

const AB_QUALITY_DEFS: { key: AbImageQuality; label: string; hint: string }[] = [
  { key: 'low', label: 'Low', hint: '≈1024 px, быстро и бюджетно' },
  { key: 'medium', label: 'Medium', hint: '≈1536–2048 px, больше деталей' },
  { key: 'high', label: 'High', hint: '≈2048 px + reasoning, максимум реализма лица' },
];

export const AB_QUALITIES: { key: AbImageQuality; label: string; hint: string }[] = AB_QUALITY_DEFS.map(
  (def) =>
    new Proxy(def, {
      get(target, prop, receiver) {
        if (prop === 'label') {
          return i18next.t(`catalog:abQualities.${target.key}.label`, target.label) || target.label;
        }
        if (prop === 'hint') {
          return i18next.t(`catalog:abQualities.${target.key}.hint`, target.hint) || target.hint;
        }
        return Reflect.get(target, prop, receiver);
      },
    }),
);

export function getAbModelCost(
  tier: AbProductTier,
  quality: AbImageQuality,
): number {
  const meta = AB_MODELS.find((m) => m.key === tier);
  return meta ? meta.cost[quality] : 0;
}

/** Вернуть кредитную стоимость режима для отображения в UI. */
export function getAbModelCreditCost(tier: AbProductTier): number {
  const meta = AB_MODELS.find((m) => m.key === tier);
  return meta ? meta.creditCost : 1;
}

/**
 * Резолвит, какую модель посылать на бэк для выбранного tier'а.
 * Всегда `gpt_image_2`; premium-tier дополнительно включает Clarity
 * Upscaler post-pass на стороне бэка.
 */
export function getImageModelForTier(tier: AbProductTier): AbImageModel {
  const meta = AB_MODELS.find((m) => m.key === tier);
  return meta?.imageModel ?? 'gpt_image_2';
}

/**
 * «1 кредит / 2 кредита» — для нижней подписи под пилюлями модели.
 * Локализуется через i18next с правилами множественного числа для
 * русской и английской раскладок.
 */
export function formatAbCredits(tier: AbProductTier): string {
  const cost = getAbModelCreditCost(tier);
  return i18next.t('catalog:creditsPerGen', { count: cost, defaultValue: `${cost} credits per generation` });
}

/** Оставлено для обратной совместимости — сейчас не вызывается из UI. */
export function formatAbCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  return `~$${value.toFixed(2)} / изображение`;
}
