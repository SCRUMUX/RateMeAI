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
 * Списание кредитов сейчас захардкожено в 1 кредит за любую генерацию
 * (см. ``src/api/deps.py::_reserve_credit_for``). Поле ``creditCost``
 * здесь — это обещание UI; реальный тарифный механизм (2 кредита за
 * премиум) подключается отдельным PR по всей цепочке reserve/refund.
 */
import type { AbImageModel, AbImageQuality } from '../lib/api';

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

export const AB_MODELS: AbModelMeta[] = [
  {
    key: 'nano_banana_2',
    label: 'Обычный режим',
    short: 'Быстрая генерация',
    description:
      'Быстрый и экономичный рендер с хорошим сохранением лица. ' +
      'Подходит для большинства стилей и типовых фото.',
    creditCost: 1,
    cost: { low: 0.08, medium: 0.12, high: 0.12 },
  },
  {
    key: 'gpt_image_2',
    label: 'Премиум',
    short: 'Максимальный реализм',
    description:
      'Максимальная адгезия промпта и «студийная» подача. Лучше для сложных ' +
      'сцен и мелких деталей. Занимает чуть больше времени.',
    creditCost: 2,
    cost: { low: 0.02, medium: 0.06, high: 0.25 },
  },
];

export const AB_QUALITIES: { key: AbImageQuality; label: string; hint: string }[] = [
  { key: 'low', label: 'Low', hint: '≈1024 px, быстро и бюджетно' },
  { key: 'medium', label: 'Medium', hint: '≈1536–2048 px, больше деталей' },
  { key: 'high', label: 'High', hint: '≈2048 px + reasoning, максимум реализма лица' },
];

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
 * Склонение числительного для слова «кредит».
 *
 * 1 — кредит, 2-4 — кредита, 5-20 — кредитов, и т.д. по стандартным
 * правилам русской грамматики.
 */
function pluralizeCredits(n: number): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return 'кредитов';
  if (last === 1) return 'кредит';
  if (last >= 2 && last <= 4) return 'кредита';
  return 'кредитов';
}

/** «1 кредит / 2 кредита» — для нижней подписи под пилюлями модели. */
export function formatAbCredits(model: AbImageModel): string {
  const cost = getAbModelCreditCost(model);
  return `${cost} ${pluralizeCredits(cost)} за генерацию`;
}

/** Оставлено для обратной совместимости — сейчас не вызывается из UI. */
export function formatAbCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  return `~$${value.toFixed(2)} / изображение`;
}
