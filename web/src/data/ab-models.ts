/**
 * v1.22 A/B-test static model catalog.
 *
 * Used by the wizard (StepGenerate) to render the "Модель" and
 * "Качество" pills and surface an honest cost-per-image hint without
 * a network roundtrip. Keep in sync with the backend defaults in
 * ``src/config.py`` (``model_cost_fal_nano_banana_*``,
 * ``model_cost_gpt_image_2_*``). v1.22 removed the "Стандарт" pill
 * entirely; these two models are the full set of user-visible
 * options.
 */
import type { AbImageModel, AbImageQuality } from '../lib/api';

export interface AbModelMeta {
  key: AbImageModel;
  label: string;
  short: string;
  description: string;
  /** USD per image, indexed by quality tier. */
  cost: Record<AbImageQuality, number>;
}

export const AB_MODELS: AbModelMeta[] = [
  {
    key: 'nano_banana_2',
    label: 'Nano Banana 2',
    short: 'Google · Gemini 3.1 Flash',
    description:
      'Быстрая i2i-модель с хорошим балансом натуральности и сохранения лица. ' +
      'Low ≈ 1024 px, Medium ≈ 2048 px, High ≈ 4096 px.',
    // fal pricing: 1K=$0.08, 2K=$0.12, 4K=$0.16.
    cost: { low: 0.08, medium: 0.12, high: 0.16 },
  },
  {
    key: 'gpt_image_2',
    label: 'GPT Image 2',
    short: 'OpenAI · ChatGPT Images 2.0',
    description:
      'Максимальная адгезия промпта и сложные сцены; фирменная «студийная» подача. ' +
      'Low ≈ 1024², Medium ≈ 1536², High ≈ 2048². Оплачивается по токенам.',
    // Empirical per-tier averages for a 1-reference portrait edit.
    cost: { low: 0.02, medium: 0.06, high: 0.25 },
  },
];

export const AB_QUALITIES: { key: AbImageQuality; label: string; hint: string }[] = [
  { key: 'low', label: 'Low', hint: '≈1024 px, дефолт — самый бюджетный' },
  { key: 'medium', label: 'Medium', hint: '≈1536–2048 px, баланс цены и детали' },
  { key: 'high', label: 'High', hint: '≈2048–4096 px, максимум деталей' },
];

export function getAbModelCost(
  model: AbImageModel,
  quality: AbImageQuality,
): number {
  const meta = AB_MODELS.find((m) => m.key === model);
  return meta ? meta.cost[quality] : 0;
}

export function formatAbCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  return `~$${value.toFixed(2)} / изображение`;
}
