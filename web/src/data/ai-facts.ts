import i18next from '../lib/i18n';
import type { CategoryId } from './styles';

export interface AiFact {
  type: 'fact';
  text: string;
}

/**
 * RU fallback set for the streaming "did you know" facts shown during
 * generation. The actual copy lives in `wizard.json` under
 * `streamFacts.<categoryId>` so each market renders its own language.
 * If i18next has no entry for a category we fall back to this map so
 * the carousel never goes silent.
 */
const FALLBACK_FACTS_BY_CATEGORY: Record<CategoryId, string[]> = {
  social: [
    'Первое впечатление формируется за 100 миллисекунд — и почти не меняется потом.',
    'Улыбающиеся лица воспринимаются на 30% более привлекательными.',
    'Зрительный контакт повышает ощущение искренности на 45%.',
    'Фото с тёплым освещением вызывают в 2 раза больше доверия.',
  ],
  cv: [
    'Резюме с профессиональным фото получают на 40% больше откликов.',
    'Рекрутеры тратят в среднем 7 секунд на первичный просмотр профиля.',
    'Деловой портрет с прямым взглядом повышает воспринимаемую компетентность на 35%.',
  ],
  dating: [
    'Теплота — главный фактор привлекательности при первой встрече.',
    'Улыбка Дюшена (искренняя) воспринимается в 10 раз привлекательнее социальной.',
    'Тёплое освещение на фото повышает воспринимаемую привлекательность на 20%.',
  ],
  model: ['Профессиональные фото в портфолио увеличивают количество приглашений на кастинги в 3 раза.'],
  brand: ['Личный бренд с качественным визуалом повышает доверие аудитории на 55%.'],
  memes: ['Мемы с лицами получают на 38% больше вовлечённости чем текстовые.'],
};

function readFactsForCategory(category: CategoryId): string[] {
  const raw = i18next.t(`wizard:streamFacts.${category}`, { returnObjects: true });
  if (Array.isArray(raw)) {
    const cleaned = raw.filter((s): s is string => typeof s === 'string' && !!s.trim());
    if (cleaned.length) return cleaned;
  }
  return FALLBACK_FACTS_BY_CATEGORY[category] ?? [];
}

function toFacts(texts: string[]): AiFact[] {
  return texts.map((text) => ({ type: 'fact', text }));
}

/**
 * @deprecated Read facts via {@link getStreamFacts} so the EN build
 * picks up the english translations. Kept for callers that still
 * access the static map at module load time.
 */
export const PERCEPTION_FACTS: Record<CategoryId, AiFact[]> = new Proxy(
  {} as Record<CategoryId, AiFact[]>,
  {
    get(_target, prop) {
      if (typeof prop !== 'string') return undefined;
      return toFacts(readFactsForCategory(prop as CategoryId));
    },
  },
);

export function getStreamFacts(category?: CategoryId): AiFact[] {
  if (category) return toFacts(readFactsForCategory(category));
  return [
    ...toFacts(readFactsForCategory('social')),
    ...toFacts(readFactsForCategory('cv')),
    ...toFacts(readFactsForCategory('dating')),
  ];
}

/**
 * 1.59.0 — removed the eager ``AI_FACTS = getStreamFacts()`` export.
 * The original module-level evaluation could fire before i18next had
 * finished loading the `wizard:streamFacts.*` resource (depends on
 * import order) and silently bake an empty array into the module
 * cache. Use {@link getStreamFacts} or {@link getRandomFact} instead —
 * both resolve through i18next on every call.
 */

export function getRandomFact(
  excludeIndex?: number,
  category?: CategoryId,
): { fact: AiFact; index: number } {
  const pool = getStreamFacts(category);
  if (!pool.length) {
    return { fact: { type: 'fact', text: '' }, index: 0 };
  }
  let idx: number;
  do {
    idx = Math.floor(Math.random() * pool.length);
  } while (idx === excludeIndex && pool.length > 1);
  return { fact: pool[idx], index: idx };
}
