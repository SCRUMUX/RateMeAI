/**
 * v1.26 A/B-test static model catalog.
 *
 * Used by the wizard (StepGenerate) to render the "Модель" pills and
 * surface an honest per-image cost to the user.
 *
 * v1.26: relabelled the two user-visible models to продуктовые «Обычный
 * режим» / «Премиум» (вместо внутренних кодовых имён Nano Banana 2 /
 * GPT Image 2) и перевели стоимость в кредиты. USD-цены per quality tier
 * остались на бэкенде (см. ``src/config.py::model_cost_*``); на фронте
 * пользователь больше видит кредитный ценник — это соответствует текущей
 * модели монетизации (пакеты кредитов, не долларов).
 *
 * v1.26.1: swap лейблов — GPT Image 2 теперь «Обычный режим» (1 кредит),
 * Nano Banana 2 — «Премиум» (2 кредита). До этого маппинг был обратным
 * и пользователи жаловались, что по нажатию «Обычный» в логах FAL видно
 * вызов Nano Banana. Default на бэке (``src/config.py::ab_default_model``)
 * уже ``gpt_image_2`` — он совпадает с новым «Обычным» без правок бэка.
 *
 * Списание кредитов сейчас захардкожено в 1 кредит за любую генерацию
 * (см. ``src/api/deps.py::_reserve_credit_for``). Поле ``creditCost``
 * здесь — это обещание UI; реальный тарифный механизм (2 кредита за
 * премиум) подключается отдельным PR по всей цепочке reserve/refund.
 */
import type { AbImageModel, AbImageQuality } from '../lib/api';
import i18next from '../lib/i18n';

export interface AbModelMeta {
  key: AbImageModel;
  label: string;
  short: string;
  description: string;
  /** Сколько кредитов пользователь видит в UI за одну генерацию. */
  creditCost: number;
  /** USD per image, indexed by quality tier — используется только в телеметрии/бэке. */
  cost: Record<AbImageQuality, number>;
}

interface AbModelDef {
  key: AbImageModel;
  /** RU-fallback используется, если ключа в catalog.json нет. */
  label: string;
  short: string;
  description: string;
  creditCost: number;
  cost: Record<AbImageQuality, number>;
}

const AB_MODEL_DEFS: AbModelDef[] = [
  {
    key: 'gpt_image_2',
    label: 'Обычный режим',
    short: 'Сбалансированный стандарт',
    description:
      'Стандартный рендер с хорошей адгезией промпта и стабильной ' +
      'передачей лица. Подходит для большинства сценариев.',
    creditCost: 1,
    cost: { low: 0.02, medium: 0.06, high: 0.25 },
  },
  {
    key: 'nano_banana_2',
    label: 'Премиум',
    short: 'Максимальное сохранение лица',
    description:
      'Премиальный рендер с акцентом на идентичность и фактуру кожи. ' +
      'Лучше для крупных планов и тонких деталей лица.',
    creditCost: 2,
    cost: { low: 0.08, medium: 0.12, high: 0.12 },
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

export function getAbModelLabel(key: AbImageModel): string {
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
  model: AbImageModel,
  quality: AbImageQuality,
): number {
  const meta = AB_MODELS.find((m) => m.key === model);
  return meta ? meta.cost[quality] : 0;
}

/** Вернуть кредитную стоимость режима для отображения в UI. */
export function getAbModelCreditCost(model: AbImageModel): number {
  const meta = AB_MODELS.find((m) => m.key === model);
  return meta ? meta.creditCost : 1;
}

/**
 * «1 кредит / 2 кредита» — для нижней подписи под пилюлями модели.
 * Локализуется через i18next с правилами множественного числа для
 * русской и английской раскладок.
 */
export function formatAbCredits(model: AbImageModel): string {
  const cost = getAbModelCreditCost(model);
  return i18next.t('catalog:creditsPerGen', { count: cost, defaultValue: `${cost} credits per generation` });
}

/** Оставлено для обратной совместимости — сейчас не вызывается из UI. */
export function formatAbCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  return `~$${value.toFixed(2)} / изображение`;
}
