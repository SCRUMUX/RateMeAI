import i18next from '../lib/i18n';
import { DOCUMENT_LANDING_ITEMS } from './landingStyles';
import { CATEGORIES, type CategoryId } from './styles';
import { FULL_LANDING_STYLES_BY_CATEGORY } from './landingStyles';
import { TESTIMONIALS } from './testimonials';

export interface SocialProofFeedItem {
  id: string;
  author: string;
  message: string;
  context: string;
}

export interface SocialProofCounterConfig {
  minDelayMs: number;
  maxDelayMs: number;
  burstChance: number;
  maxBurstSize: number;
}

export interface SocialProofPreset {
  id: CategoryId | 'documents';
  title: string;
  baseCount: number;
  counter: SocialProofCounterConfig;
  tickerIntervalMs: number;
  feed: SocialProofFeedItem[];
}

/**
 * 1.59.0 — copy moved into the ``socialProof`` i18n namespace, but
 * the numeric pacing knobs (counter delays, base counts, ticker
 * intervals) stay in code: they are pure presentation tuning and
 * never need to be translated.
 */
const HOME_PACING: Record<CategoryId, Omit<SocialProofPreset, 'id' | 'feed' | 'title'>> = {
  social: {
    baseCount: 2734,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.1, maxBurstSize: 3 },
    tickerIntervalMs: 4200,
  },
  cv: {
    baseCount: 2481,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.1, maxBurstSize: 3 },
    tickerIntervalMs: 4300,
  },
  dating: {
    baseCount: 2916,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.12, maxBurstSize: 3 },
    tickerIntervalMs: 3900,
  },
  model: {
    baseCount: 1864,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.08, maxBurstSize: 2 },
    tickerIntervalMs: 4500,
  },
  brand: {
    baseCount: 2017,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.08, maxBurstSize: 2 },
    tickerIntervalMs: 4400,
  },
  memes: {
    baseCount: 1679,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.12, maxBurstSize: 3 },
    tickerIntervalMs: 4000,
  },
};

function homeTitleFor(category: CategoryId): string {
  const v = i18next.t(`socialProof:home.${category}`);
  return typeof v === 'string' && v.trim() ? v : '';
}

function categoryMessages(category: CategoryId): string[] {
  const raw = i18next.t(`socialProof:categoryMessages.${category}`, { returnObjects: true });
  if (Array.isArray(raw)) {
    return raw.filter((s): s is string => typeof s === 'string' && !!s.trim());
  }
  return [];
}

function documentsGenericMessages(): string[] {
  const raw = i18next.t('socialProof:documents.genericMessages', { returnObjects: true });
  if (Array.isArray(raw)) {
    return raw.filter((s): s is string => typeof s === 'string' && !!s.trim());
  }
  return [];
}

const FALLBACK_AUTHORS = {
  social: ['@viki.frame', '@den.content', '@sasha.reels', '@mila.daily', '@roma.feed'],
  cv: ['@irina.hr', '@pavel.pm', '@anna.cv', '@nikita.team', '@olga.lead'],
  dating: ['@masha.match', '@egor.date', '@alina.hello', '@denis.swipe', '@rita.vibe'],
  model: ['@lena.portfolio', '@yan.frame', '@mila.lookbook', '@alex.cast', '@nina.studio'],
  brand: ['@max.expert', '@yana.voice', '@igor.brand', '@kate.founder', '@daria.media'],
  documents: ['@passport_case', '@visa_ready', '@docs.fast', '@photo_form', '@paperwork_ok'],
  memes: ['@meme.drop', '@lol.edit', '@vibe.reply', '@clip.energy', '@justwow'],
} as const;

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function getStyleName(category: CategoryId, styleKey: string): string {
  const fallback = i18next.t('socialProof:fallbackStyleName');
  return (
    FULL_LANDING_STYLES_BY_CATEGORY[category].find((style) => style.key === styleKey)?.name
    ?? (typeof fallback === 'string' ? fallback : 'New style')
  );
}

function buildTestimonialFeed(category: CategoryId): SocialProofFeedItem[] {
  const categoryLabel = CATEGORIES.find((item) => item.id === category)?.label ?? capitalize(category);
  const categoryTestimonials = TESTIMONIALS.filter((item) => item.category === category);
  const messages = categoryMessages(category);
  const aiCtx = i18next.t('socialProof:feedContexts.aiAnalysis');
  const recentCtx = i18next.t('socialProof:feedContexts.recentImpression');

  const derived = categoryTestimonials.flatMap((item, index) => {
    const styleName = getStyleName(category, item.styleKey);
    const beforeScore = item.beforeScore.toFixed(2);
    const afterScore = item.afterScore.toFixed(2);

    return [
      {
        id: `${item.id}-review`,
        author: item.nickname,
        message: item.shortReview,
        context: `${categoryLabel} · ${styleName}`,
      },
      {
        id: `${item.id}-score`,
        author: item.nickname,
        message: i18next.t('socialProof:feedTemplates.styleScore', {
          styleName,
          before: beforeScore,
          after: afterScore,
        }) as string,
        context: `${categoryLabel} · ${aiCtx}`,
      },
      {
        id: `${item.id}-effect`,
        author: item.nickname,
        message:
          messages[index]
          ?? (i18next.t('socialProof:feedTemplates.styleEffect', { styleName }) as string),
        context: `${categoryLabel} · ${styleName}`,
      },
    ];
  });

  const extras = messages.map((message, index) => ({
    id: `${category}-extra-${index}`,
    author: FALLBACK_AUTHORS[category][index % FALLBACK_AUTHORS[category].length],
    message,
    context: `${categoryLabel} · ${recentCtx}`,
  }));

  return [...derived, ...extras];
}

function buildComingSoonFeed(category: CategoryId): SocialProofFeedItem[] {
  const categoryLabel = CATEGORIES.find((item) => item.id === category)?.label ?? capitalize(category);
  const styles = FULL_LANDING_STYLES_BY_CATEGORY[category].slice(0, 5);
  const previewCtx = i18next.t('socialProof:feedContexts.preview');
  const earlyCtx = i18next.t('socialProof:feedContexts.earlyAccess');

  const styleMessages = styles.flatMap((style, index) => [
    {
      id: `${category}-${style.key}-1`,
      author: FALLBACK_AUTHORS[category][index % FALLBACK_AUTHORS[category].length],
      message: i18next.t('socialProof:feedTemplates.comingSoonStrong', { styleName: style.name }) as string,
      context: `${categoryLabel} · ${style.name}`,
    },
    {
      id: `${category}-${style.key}-2`,
      author: FALLBACK_AUTHORS[category][(index + 1) % FALLBACK_AUTHORS[category].length],
      message: style.desc,
      context: `${categoryLabel} · ${style.name}`,
    },
    {
      id: `${category}-${style.key}-3`,
      author: FALLBACK_AUTHORS[category][(index + 2) % FALLBACK_AUTHORS[category].length],
      message: i18next.t('socialProof:feedTemplates.comingSoonVibe', { styleName: style.name }) as string,
      context: `${categoryLabel} · ${previewCtx}`,
    },
  ]);

  const extras = categoryMessages(category).map((message, index) => ({
    id: `${category}-coming-extra-${index}`,
    author: FALLBACK_AUTHORS[category][index % FALLBACK_AUTHORS[category].length],
    message,
    context: `${categoryLabel} · ${earlyCtx}`,
  }));

  return [...styleMessages, ...extras];
}

function buildDocumentFeed(): SocialProofFeedItem[] {
  const docLabel = i18next.t('socialProof:documents.label') as string;
  const recentReview = i18next.t('socialProof:feedContexts.recentReview') as string;
  const recentImpression = i18next.t('socialProof:feedContexts.recentDocImpression') as string;

  const derived = DOCUMENT_LANDING_ITEMS.flatMap((item, index) => [
    {
      id: `documents-${item.key}-main`,
      author: FALLBACK_AUTHORS.documents[index % FALLBACK_AUTHORS.documents.length],
      message: i18next.t('socialProof:feedTemplates.documentMain', { name: item.name }) as string,
      context: `${docLabel} · ${item.name}`,
    },
    {
      id: `documents-${item.key}-desc`,
      author: FALLBACK_AUTHORS.documents[(index + 1) % FALLBACK_AUTHORS.documents.length],
      message: item.desc,
      context: `${docLabel} · ${item.usage}`,
    },
    {
      id: `documents-${item.key}-effect`,
      author: FALLBACK_AUTHORS.documents[(index + 2) % FALLBACK_AUTHORS.documents.length],
      message: i18next.t('socialProof:feedTemplates.documentEffect', { name: item.name }) as string,
      context: `${docLabel} · ${recentReview}`,
    },
  ]);

  const extras = documentsGenericMessages().map((message, index) => ({
    id: `documents-extra-${index}`,
    author: FALLBACK_AUTHORS.documents[index % FALLBACK_AUTHORS.documents.length],
    message,
    context: `${docLabel} · ${recentImpression}`,
  }));

  return [...derived, ...extras];
}

export function getLandingSocialProofPreset(category: CategoryId): SocialProofPreset {
  const pacing = HOME_PACING[category];
  const feed = TESTIMONIALS.some((item) => item.category === category)
    ? buildTestimonialFeed(category)
    : buildComingSoonFeed(category);

  return {
    id: category,
    title: homeTitleFor(category),
    ...pacing,
    feed,
  };
}

/**
 * 1.59.0 — DOCUMENT_SOCIAL_PROOF_PRESET is now a getter so the i18n
 * lookups happen lazily (after i18next has finished initialising).
 * Module-level eager evaluation produced empty strings on the EN
 * build because the import order ran this file before the resource
 * bundles were attached.
 */
export function getDocumentSocialProofPreset(): SocialProofPreset {
  return {
    id: 'documents',
    title: i18next.t('socialProof:documents.title') as string,
    baseCount: 3186,
    counter: { minDelayMs: 5000, maxDelayMs: 10000, burstChance: 0.08, maxBurstSize: 2 },
    tickerIntervalMs: 4300,
    feed: buildDocumentFeed(),
  };
}

/**
 * Backwards-compatible export: callers that destructure
 * ``DOCUMENT_SOCIAL_PROOF_PRESET`` (e.g. VisaLanding for the proof
 * counter pacing) keep working. Each property access reads through
 * the getter, so the bundle never freezes a stale empty title.
 */
export const DOCUMENT_SOCIAL_PROOF_PRESET: SocialProofPreset = new Proxy(
  {} as SocialProofPreset,
  {
    get(_target, prop) {
      const live = getDocumentSocialProofPreset();
      return live[prop as keyof SocialProofPreset];
    },
  },
);
