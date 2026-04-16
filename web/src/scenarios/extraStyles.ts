import type { StyleItem } from '../data/styles';

/** Extra dating styles merged into main app + available on /app/tinder-pack */
export const TINDER_PACK_STYLE_ITEMS: StyleItem[] = [
  {
    key: 'tinder_pack_rooftop_golden',
    icon: '🌆',
    name: 'Руфтоп золотой час',
    desc: 'Тёплый городской закат для максимального свайпа вправо',
    param: 'appeal',
    deltaRange: [0.48, 0.72],
  },
  {
    key: 'tinder_pack_minimal_studio',
    icon: '✨',
    name: 'Минимал студия',
    desc: 'Чистый портрет без отвлекающих деталей',
    param: 'appeal',
    deltaRange: [0.42, 0.65],
  },
  {
    key: 'tinder_pack_cafe_window',
    icon: '☕',
    name: 'Кафе у окна',
    desc: 'Уютный свет и естественная улыбка',
    param: 'warmth',
    deltaRange: [0.35, 0.55],
  },
];

export interface DocumentFormatItem extends StyleItem {
  usage: string;
}

export const DOCUMENT_FORMAT_ITEMS: DocumentFormatItem[] = [
  {
    key: 'photo_3x4',
    icon: '📋',
    name: '3×4 стандарт',
    desc: '30×40 мм, лицо 70–80%, нейтральное выражение',
    usage: 'Пропуска, медкнижка, студенческий, удостоверения',
    param: 'trust',
    deltaRange: [0.02, 0.05],
  },
  {
    key: 'passport_rf',
    icon: '🛂',
    name: 'Паспорт РФ',
    desc: '35×45 мм, строго фронтально, белый фон',
    usage: 'Внутренний паспорт РФ',
    param: 'trust',
    deltaRange: [0.02, 0.05],
  },
  {
    key: 'visa_eu',
    icon: '✈️',
    name: 'Виза / Шенген',
    desc: '35×45 мм, лицо 70–80%, без теней',
    usage: 'Визы, загранпаспорт',
    param: 'trust',
    deltaRange: [0.02, 0.05],
  },
  {
    key: 'visa_us',
    icon: '🌐',
    name: 'Виза США',
    desc: '50×50 мм, квадрат, голова 25–35 мм',
    usage: 'Виза США',
    param: 'trust',
    deltaRange: [0.02, 0.05],
  },
  {
    key: 'photo_4x6',
    icon: '📷',
    name: '4×6 универсал',
    desc: '40×60 мм, менее строгие требования',
    usage: 'Анкеты, личные дела',
    param: 'trust',
    deltaRange: [0.02, 0.05],
  },
];

export function isDocumentFormatItem(item: StyleItem): item is DocumentFormatItem {
  return 'usage' in item && typeof (item as DocumentFormatItem).usage === 'string';
}
