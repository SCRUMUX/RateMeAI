import { PARAMS_BY_MODE, type CategoryId, type StyleItem } from '../../data/styles';

export const STYLES_PER_PAGE = 8;



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
