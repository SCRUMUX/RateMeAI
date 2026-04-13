import { PARAMS_BY_MODE, type CategoryId, type StyleItem } from '../../data/styles';

export type GenSimMode = 'demo' | 'no_credits' | 'real';

export const STYLES_PER_PAGE = 8;

export const FIXED_DURATION = 27;

export const GEN_SIM_STEPS = [
  'Загрузка нейросети...',
  'Анализ структуры лица...',
  'Подбор параметров стиля...',
  'Генерация вариантов...',
  'Оптимизация деталей...',
  'Финальная обработка...',
];

export const SIM_TEXTS: Record<number, string> = {
  0: 'AI анализирует ваше фото по ключевым параметрам восприятия. Каждый стиль адаптирует образ под конкретный контекст, улучшая целевые метрики.',
  1: 'Определяем ключевые черты лица и выражение...',
  2: 'Оцениваем параметры восприятия: теплота, уверенность, привлекательность...',
  3: 'Формируем персонализированные рекомендации...',
  4: 'Произведён анализ фото с точки зрения психологии восприятия. Подобраны оптимальные параметры улучшения для выбранного контекста.',
};

export const PARAM_LABELS: Record<string, string> = {
  warmth: 'Теплота',
  presence: 'Уверенность',
  appeal: 'Привлекательность',
  trust: 'Доверие',
  competence: 'Компетентность',
  hireability: 'Найм',
  social_score: 'Social Score',
  dating_score: 'Dating Score',
  authenticity: 'Аутентичность',
};

export function computeStyleDeltas(style: StyleItem, tab: CategoryId): Record<string, number> {
  const avgDelta = (style.deltaRange[0] + style.deltaRange[1]) / 2;
  const params = PARAMS_BY_MODE[tab];
  const result: Record<string, number> = {};
  const primaryShare = 0.6;
  const othersShare = 0.4 / Math.max(params.length - 1, 1);
  for (const p of params) {
    result[p.key] = p.key === style.param
      ? +(avgDelta * primaryShare).toFixed(2)
      : +(avgDelta * othersShare).toFixed(2);
  }
  return result;
}

export const WIZARD_STEPS = [
  { id: 'upload' as const, number: 1, title: 'Загрузка', desc: 'Загрузите фото' },
  { id: 'analysis' as const, number: 2, title: 'Анализ', desc: 'AI-анализ восприятия' },
  { id: 'style' as const, number: 3, title: 'Стиль', desc: 'Выберите стиль' },
  { id: 'generate' as const, number: 4, title: 'Результат', desc: 'Генерация и результат' },
] as const;

export type WizardStepId = typeof WIZARD_STEPS[number]['id'];
