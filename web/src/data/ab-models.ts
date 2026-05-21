/**
 * v1.72 продуктовый tier-каталог. Сменил модельный A/B-выбор (Nano
 * Banana 2 vs GPT Image 2) на единые продуктовые tier'ы «Стандарт /
 * Премиум».
 *
 * История
 * --------
 * v1.26 — впервые ввели «Обычный режим» / «Премиум» как UI-обёртку
 * над `image_model`. Кнопка «Премиум» фактически переключала бэк
 * на Nano Banana 2 (medium ~$0.12/img). Биллинг тогда был
 * захардкожен в 1 кредит независимо от выбора.
 *
 * v1.72 — клиент пожаловался, что «премиум на Nano Banana 2 дороже,
 * но не лучше». Поменяли продуктовое значение:
 *   * «Стандарт»  → `image_model=gpt_image_2`, `image_quality=medium`,
 *                   без refiner-а. ≈ $0.06/img. 1 кредит.
 *   * «Премиум»   → `image_model=gpt_image_2`, `image_quality=medium`
 *                   + Clarity Upscaler refiner post-pass. ≈ $0.10/img.
 *                   2 кредита (теперь реально списывается двойная
 *                   стоимость, см. ``src/api/deps.py::_reserve_credit_for``;
 *                   refund 1 кредит если refiner упал).
 *
 * Структурно оба tier'а посылают `image_model=gpt_image_2`; запрос
 * на бэк дополнительно несёт `tier=standard|premium`. Бэк (см.
 * ``src/services/analysis_request.py::apply_ab_test_context_fields``)
 * на premium-tier'е жёстко перезаписывает `image_model` на
 * `gpt_image_2`, чтобы клиент не мог получить премиум-биллинг с
 * Nano Banana рендером.
 */
import type { AbImageModel, AbImageQuality, AbProductTier } from '../lib/api';
import i18next from '../lib/i18n';

export interface AbModelMeta {
  /** Внутренний идентификатор tier'а (тот же, что и `AbProductTier`). */
  key: AbProductTier;
  /** Какую модель посылать на бэк. После v1.72 — всегда `gpt_image_2`. */
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
    cost: { low: 0.02, medium: 0.06, high: 0.25 },
  },
  {
    key: 'premium',
    imageModel: 'gpt_image_2',
    label: 'Премиум',
    short: 'Резче детали и пиксельная проработка',
    description:
      'Тот же базовый рендер GPT Image 2 medium, но с дополнительным ' +
      'проходом Clarity Upscaler: подтягивает чёткость текстуры кожи, ' +
      'волос и фона без изменения композиции и идентичности.',
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
 * После v1.72 всегда `gpt_image_2` (premium-tier добавляет refiner
 * post-pass, но базовая модель та же).
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
