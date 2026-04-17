import { DOCUMENT_FORMAT_ITEMS } from '../scenarios/extraStyles';
import { CATEGORIES, STYLES_BY_CATEGORY, type CategoryId } from './styles';
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

const HOME_COPY: Record<CategoryId, Omit<SocialProofPreset, 'id' | 'feed'>> = {
  social: {
    title: 'Люди уже улучшили свои фото для соцсетей',
    baseCount: 2734,
    counter: {
      minDelayMs: 8000,
      maxDelayMs: 36000,
      burstChance: 0.16,
      maxBurstSize: 3,
    },
    tickerIntervalMs: 4200,
  },
  cv: {
    title: 'Люди уже улучшили свои фото для карьеры',
    baseCount: 2481,
    counter: {
      minDelayMs: 10000,
      maxDelayMs: 42000,
      burstChance: 0.14,
      maxBurstSize: 2,
    },
    tickerIntervalMs: 4300,
  },
  dating: {
    title: 'Люди уже улучшили свои фото для знакомств',
    baseCount: 2916,
    counter: {
      minDelayMs: 7000,
      maxDelayMs: 30000,
      burstChance: 0.2,
      maxBurstSize: 3,
    },
    tickerIntervalMs: 3900,
  },
  model: {
    title: 'Люди уже следят за новыми фотосет-сценариями',
    baseCount: 1864,
    counter: {
      minDelayMs: 14000,
      maxDelayMs: 52000,
      burstChance: 0.12,
      maxBurstSize: 2,
    },
    tickerIntervalMs: 4500,
  },
  brand: {
    title: 'Люди уже готовят новые фото для личного бренда',
    baseCount: 2017,
    counter: {
      minDelayMs: 12000,
      maxDelayMs: 46000,
      burstChance: 0.14,
      maxBurstSize: 2,
    },
    tickerIntervalMs: 4400,
  },
  memes: {
    title: 'Люди уже ждут запуск новых мем-сценариев',
    baseCount: 1679,
    counter: {
      minDelayMs: 9000,
      maxDelayMs: 32000,
      burstChance: 0.18,
      maxBurstSize: 3,
    },
    tickerIntervalMs: 4000,
  },
};

const CATEGORY_EXTRA_MESSAGES: Record<CategoryId, string[]> = {
  social: [
    'Сразу появилось ощущение контента, который хочется досмотреть.',
    'Фото стало выглядеть так, будто над ним работал контент-креатор.',
    'В ленте кадр стал цеплять заметно быстрее.',
    'Теперь легче держать единый визуальный вайб аккаунта.',
    'Даже обычное селфи стало выглядеть как сильный пост.',
  ],
  cv: [
    'Первое впечатление стало заметно более собранным и уверенным.',
    'Такой визуал не отвлекает, а усиливает доверие к профилю.',
    'Для LinkedIn и резюме это ощущается намного сильнее обычного селфи.',
    'Фото стало выглядеть профессионально без лишней искусственности.',
    'С этим образом проще заходить в рабочие и экспертные сценарии.',
  ],
  dating: [
    'Анкета стала выглядеть теплее и заметно живее.',
    'Появился тот самый вайб легкого знакомства без перегруза.',
    'Фото выглядит уверенно, но не слишком постановочно.',
    'Визуал стал располагать к первому сообщению.',
    'Профиль начал выглядеть дороже и естественнее одновременно.',
  ],
  model: [
    'Свет и подача ощущаются как начало полноценного фотосета.',
    'Даже в ранних сценариях уже видна студийная подача.',
    'Такой визуал легко представить в портфолио.',
    'Фон и свет собирают образ намного сильнее.',
    'Сценарий выглядит как хорошая база для съемки.',
  ],
  brand: [
    'Визуал сразу начинает работать на позиционирование.',
    'Подача ощущается увереннее и взрослее.',
    'Такой образ хорошо ложится в экспертный контент.',
    'Появилось ощущение цельного личного бренда.',
    'Фото лучше поддерживает голос и статус бренда.',
  ],
  memes: [
    'С первого взгляда считывается вайб и шутка.',
    'Контент выглядит живее и вируснее.',
    'Образ быстро вызывает реакцию и эмоцию.',
    'Для мем-формата это очень цепляющая подача.',
    'Даже превью стало ощущаться бодрее.',
  ],
};

const DOCUMENT_GENERIC_MESSAGES = [
  'Получилось аккуратно и без ощущения фотосалона.',
  'Формат выглядит строго, но при этом естественно.',
  'Хорошо, что можно быстро подобрать нужный тип документа.',
  'Важнее всего, что лицо сохранилось узнаваемым.',
  'Для документов такой спокойный и чистый результат особенно важен.',
];

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
  return STYLES_BY_CATEGORY[category].find((style) => style.key === styleKey)?.name ?? 'Новый стиль';
}

function buildTestimonialFeed(category: CategoryId): SocialProofFeedItem[] {
  const categoryLabel = CATEGORIES.find((item) => item.id === category)?.label ?? capitalize(category);
  const categoryTestimonials = TESTIMONIALS.filter((item) => item.category === category);

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
        message: `После стиля «${styleName}» скор вырос с ${beforeScore} до ${afterScore}.`,
        context: `${categoryLabel} · AI анализ`,
      },
      {
        id: `${item.id}-effect`,
        author: item.nickname,
        message: CATEGORY_EXTRA_MESSAGES[category][index] ?? `Стиль «${styleName}» заметно усилил первое впечатление.`,
        context: `${categoryLabel} · ${styleName}`,
      },
    ];
  });

  const extras = CATEGORY_EXTRA_MESSAGES[category].map((message, index) => ({
    id: `${category}-extra-${index}`,
    author: FALLBACK_AUTHORS[category][index % FALLBACK_AUTHORS[category].length],
    message,
    context: `${categoryLabel} · Недавнее впечатление`,
  }));

  return [...derived, ...extras];
}

function buildComingSoonFeed(category: CategoryId): SocialProofFeedItem[] {
  const categoryLabel = CATEGORIES.find((item) => item.id === category)?.label ?? capitalize(category);
  const styles = STYLES_BY_CATEGORY[category].slice(0, 5);

  const styleMessages = styles.flatMap((style, index) => [
    {
      id: `${category}-${style.key}-1`,
      author: FALLBACK_AUTHORS[category][index % FALLBACK_AUTHORS[category].length],
      message: `Сценарий «${style.name}» уже выглядит как сильная идея для запуска.`,
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
      message: `У «${style.name}» очень сильный вайб для первого впечатления.`,
      context: `${categoryLabel} · preview`,
    },
  ]);

  const extras = CATEGORY_EXTRA_MESSAGES[category].map((message, index) => ({
    id: `${category}-coming-extra-${index}`,
    author: FALLBACK_AUTHORS[category][index % FALLBACK_AUTHORS[category].length],
    message,
    context: `${categoryLabel} · ранний доступ`,
  }));

  return [...styleMessages, ...extras];
}

function buildDocumentFeed(): SocialProofFeedItem[] {
  const derived = DOCUMENT_FORMAT_ITEMS.flatMap((item, index) => [
    {
      id: `documents-${item.key}-main`,
      author: FALLBACK_AUTHORS.documents[index % FALLBACK_AUTHORS.documents.length],
      message: `Сделал формат «${item.name}» без поездки в фотосалон.`,
      context: `Документы · ${item.name}`,
    },
    {
      id: `documents-${item.key}-desc`,
      author: FALLBACK_AUTHORS.documents[(index + 1) % FALLBACK_AUTHORS.documents.length],
      message: item.desc,
      context: `Документы · ${item.usage}`,
    },
    {
      id: `documents-${item.key}-effect`,
      author: FALLBACK_AUTHORS.documents[(index + 2) % FALLBACK_AUTHORS.documents.length],
      message: `Удобно, что формат «${item.name}» сразу выглядит спокойно и аккуратно.`,
      context: `Документы · недавний отзыв`,
    },
  ]);

  const extras = DOCUMENT_GENERIC_MESSAGES.map((message, index) => ({
    id: `documents-extra-${index}`,
    author: FALLBACK_AUTHORS.documents[index % FALLBACK_AUTHORS.documents.length],
    message,
    context: 'Документы · недавнее впечатление',
  }));

  return [...derived, ...extras];
}

export function getLandingSocialProofPreset(category: CategoryId): SocialProofPreset {
  const basePreset = HOME_COPY[category];
  const feed = TESTIMONIALS.some((item) => item.category === category)
    ? buildTestimonialFeed(category)
    : buildComingSoonFeed(category);

  return {
    id: category,
    ...basePreset,
    feed,
  };
}

export const DOCUMENT_SOCIAL_PROOF_PRESET: SocialProofPreset = {
  id: 'documents',
  title: 'Люди уже подготовили свои фото для документов',
  baseCount: 3186,
  counter: {
    minDelayMs: 11000,
    maxDelayMs: 42000,
    burstChance: 0.12,
    maxBurstSize: 2,
  },
  tickerIntervalMs: 4300,
  feed: buildDocumentFeed(),
};
