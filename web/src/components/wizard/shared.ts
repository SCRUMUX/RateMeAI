import { PARAMS_BY_MODE, type CategoryId, type StyleItem } from '../../data/styles';
import type { ScenarioStep3Mode } from '../../scenarios/config';

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

export interface WizardStep {
  id: WizardStepId;
  number: number;
  title: string;
  desc: string;
}

export const WIZARD_STEPS: readonly WizardStep[] = [
  { id: 'upload', number: 1, title: 'Загрузка', desc: 'Загрузите фото' },
  { id: 'analysis', number: 2, title: 'Анализ', desc: 'AI-анализ восприятия' },
  { id: 'style', number: 3, title: 'Стиль', desc: 'Выберите стиль' },
  { id: 'generate', number: 4, title: 'Результат', desc: 'Генерация и результат' },
];

export type WizardStepId = 'upload' | 'analysis' | 'style' | 'generate';

export function getWizardStepsForScenario(step3Mode: ScenarioStep3Mode | null): readonly WizardStep[] {
  if (step3Mode === 'document_formats') {
    return [
      { id: 'upload', number: 1, title: 'Загрузка', desc: 'Загрузите фото' },
      { id: 'analysis', number: 2, title: 'Анализ', desc: 'AI-анализ' },
      { id: 'style', number: 3, title: 'Формат', desc: 'Выберите формат' },
      { id: 'generate', number: 4, title: 'Результат', desc: 'Генерация и скачивание' },
    ];
  }
  return WIZARD_STEPS;
}
