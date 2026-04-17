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
  heartChance: number;
}

export interface SocialProofPreset {
  id: CategoryId | 'documents';
  eyebrow: string;
  title: string;
  description: string;
  tickerLabel: string;
  statLabel: string;
  statSubLabel: string;
  baseCount: number;
  highlights: string[];
  counter: SocialProofCounterConfig;
  tickerIntervalMs: number;
  feedVisibleCount: number;
  feed: SocialProofFeedItem[];
}

const HOME_COPY: Record<CategoryId, Omit<SocialProofPreset, 'id' | 'feed'>> = {
  social: {
    eyebrow: 'Живой social proof',
    title: 'Лента выглядит живой, когда фото реально цепляют внимание.',
    description: 'Показываем не сухие обещания, а поток коротких впечатлений о том, как AI-образы помогают выделяться в соцсетях.',
    tickerLabel: 'Что пишут после генераций',
    statLabel: 'человекам уже понравился новый визуал',
    statSubLabel: 'Средний темп: около 1000 позитивных реакций в сутки.',
    baseCount: 2734,
    highlights: ['Соцсети', 'Stories и posts', 'Живые реакции'],
    counter: {
      minDelayMs: 8000,
      maxDelayMs: 36000,
      burstChance: 0.16,
      maxBurstSize: 3,
      heartChance: 0.72,
    },
    tickerIntervalMs: 2600,
    feedVisibleCount: 4,
  },
  cv: {
    eyebrow: 'Живой social proof',
    title: 'Профессиональный образ работает лучше, когда ему сразу верят.',
    description: 'Блок собирает короткие впечатления о карьерных и экспертных сценариях: доверие, уверенность, отклики и качество первого контакта.',
    tickerLabel: 'Что отмечают в карьерных сценариях',
    statLabel: 'пользователей уже усилили рабочий образ',
    statSubLabel: 'Рост идет неровно, чтобы блок ощущался как живая активность, а не как таймер.',
    baseCount: 2481,
    highlights: ['Карьера', 'LinkedIn и CV', 'Первое впечатление'],
    counter: {
      minDelayMs: 10000,
      maxDelayMs: 42000,
      burstChance: 0.14,
      maxBurstSize: 2,
      heartChance: 0.58,
    },
    tickerIntervalMs: 2900,
    feedVisibleCount: 4,
  },
  dating: {
    eyebrow: 'Живой social proof',
    title: 'Для знакомств решает не только фото, а то, какое чувство оно вызывает.',
    description: 'Здесь блок создает ощущение живого продукта: теплые впечатления, рост мэтчей и визуал, который хочется свайпнуть вправо.',
    tickerLabel: 'Что пишут после обновления анкеты',
    statLabel: 'человекам уже зашел новый dating-визуал',
    statSubLabel: 'Темп роста специально неровный, чтобы цифра ощущалась естественной.',
    baseCount: 2916,
    highlights: ['Dating', 'Мэтчи и лайки', 'Первое впечатление'],
    counter: {
      minDelayMs: 7000,
      maxDelayMs: 30000,
      burstChance: 0.2,
      maxBurstSize: 3,
      heartChance: 0.82,
    },
    tickerIntervalMs: 2400,
    feedVisibleCount: 4,
  },
  model: {
    eyebrow: 'Живой social proof',
    title: 'Даже тестовые фотосет-сценарии уже создают ощущение студийной работы.',
    description: 'Для будущих фотосессионных сценариев показываем поток коротких впечатлений о подаче, свете и портфолио-визуале.',
    tickerLabel: 'Ранние впечатления по фотосетам',
    statLabel: 'человек следят за запуском фотосет-сценариев',
    statSubLabel: 'Блок уже подстраивается под будущую категорию и ее акцентный цвет.',
    baseCount: 1864,
    highlights: ['Фотосессия', 'Портфолио', 'Свет и подача'],
    counter: {
      minDelayMs: 14000,
      maxDelayMs: 52000,
      burstChance: 0.12,
      maxBurstSize: 2,
      heartChance: 0.45,
    },
    tickerIntervalMs: 3200,
    feedVisibleCount: 4,
  },
  brand: {
    eyebrow: 'Живой social proof',
    title: 'Личный бренд становится убедительнее, когда визуал звучит как позиция.',
    description: 'Показываем поток коротких реакций на сценарии для экспертов, лидеров мнений и медийного личного бренда.',
    tickerLabel: 'Ранние впечатления по личному бренду',
    statLabel: 'пользователей ждут запуск brand-сценариев',
    statSubLabel: 'Этот блок заранее подхватывает tone of voice будущего сервиса.',
    baseCount: 2017,
    highlights: ['Личный бренд', 'Экспертность', 'Медийный образ'],
    counter: {
      minDelayMs: 12000,
      maxDelayMs: 46000,
      burstChance: 0.14,
      maxBurstSize: 2,
      heartChance: 0.5,
    },
    tickerIntervalMs: 3000,
    feedVisibleCount: 4,
  },
  memes: {
    eyebrow: 'Живой social proof',
    title: 'Даже мем-сценарии выглядят сильнее, когда у них есть темп и реакция.',
    description: 'Для развлекательного направления показываем быстрые впечатления про вайб, юмор и цепляющий визуал.',
    tickerLabel: 'Ранние впечатления по мем-сценариям',
    statLabel: 'человек следят за запуском мем-режима',
    statSubLabel: 'Драйв блока усиливает ощущение живого продукта даже у coming soon категорий.',
    baseCount: 1679,
    highlights: ['Мемы', 'Вайб', 'Вирусность'],
    counter: {
      minDelayMs: 9000,
      maxDelayMs: 32000,
      burstChance: 0.18,
      maxBurstSize: 3,
      heartChance: 0.66,
    },
    tickerIntervalMs: 2500,
    feedVisibleCount: 4,
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
  eyebrow: 'Живой social proof',
  title: 'Даже фото на документы воспринимается лучше, когда видно, что сервисом реально пользуются.',
  description: 'Для документного сценария блок показывает спокойные, прикладные впечатления: нужные форматы, аккуратный результат и естественное лицо без салонной суеты.',
  tickerLabel: 'Недавние впечатления по документам',
  statLabel: 'человек уже подготовили фото для документов',
  statSubLabel: 'Счетчик обновляется неровно, а лента держит ощущение живого продукта без агрессивного маркетинга.',
  baseCount: 3186,
  highlights: ['Паспорт и визы', 'Спокойный результат', 'Нужные форматы'],
  counter: {
    minDelayMs: 11000,
    maxDelayMs: 42000,
    burstChance: 0.12,
    maxBurstSize: 2,
    heartChance: 0.4,
  },
  tickerIntervalMs: 3000,
  feedVisibleCount: 4,
  feed: buildDocumentFeed(),
};
