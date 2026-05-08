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

/**
 * Wizard step ids share i18n: titles/descs live in
 * ``locales/{ru,en}/wizard.json`` under ``stepBar.titles`` and
 * ``stepBar.descs``. Each step carries i18n *keys* — the rendering
 * component (StepBar) resolves them through ``useTranslation``.
 */
export interface WizardStep {
  id: WizardStepId;
  number: number;
  /** ``stepBar.titles.<key>`` — short title rendered under the circle. */
  titleKey: string;
  /** ``stepBar.descs.<key>`` — secondary line under the title. */
  descKey: string;
}

export const WIZARD_STEPS: readonly WizardStep[] = [
  { id: 'upload', number: 1, titleKey: 'upload', descKey: 'upload' },
  { id: 'analysis', number: 2, titleKey: 'analysis', descKey: 'analysis' },
  { id: 'style', number: 3, titleKey: 'style', descKey: 'style' },
  { id: 'generate', number: 4, titleKey: 'generate', descKey: 'generate' },
];

export type WizardStepId = 'upload' | 'analysis' | 'style' | 'generate';

export function getWizardStepsForScenario(step3Mode: ScenarioStep3Mode | null): readonly WizardStep[] {
  if (step3Mode === 'document_formats') {
    return [
      { id: 'upload', number: 1, titleKey: 'upload', descKey: 'upload' },
      { id: 'analysis', number: 2, titleKey: 'analysis', descKey: 'analysisShort' },
      { id: 'style', number: 3, titleKey: 'format', descKey: 'format' },
      { id: 'generate', number: 4, titleKey: 'generate', descKey: 'generateDownload' },
    ];
  }
  return WIZARD_STEPS;
}
