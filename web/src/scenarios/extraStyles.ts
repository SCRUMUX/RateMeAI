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
    key: 'docfmt_passport_rf',
    icon: '🪪',
    name: 'Паспорт РФ',
    desc: 'Головной портрет 35×45 мм, нейтральное выражение',
    usage: 'Загранпаспорт, оформление паспорта, госуслуги',
    param: 'trust',
    deltaRange: [0.05, 0.1],
  },
  {
    key: 'docfmt_visa_schengen',
    icon: '🇪🇺',
    name: 'Виза Шенген',
    desc: 'Светлый фон, лицо 70–80% кадра, без теней',
    usage: 'Консульства ЕС, визовые центры',
    param: 'trust',
    deltaRange: [0.05, 0.1],
  },
  {
    key: 'docfmt_us_passport',
    icon: '🇺🇸',
    name: 'USA passport / visa',
    desc: 'Белый фон, прямой взгляд, чёткий портрет',
    usage: 'DS-160, виза США, паспорт США',
    param: 'trust',
    deltaRange: [0.05, 0.1],
  },
  {
    key: 'docfmt_driver_rf',
    icon: '🚗',
    name: 'Водительское РФ',
    desc: 'Формальный вид, ровное освещение',
    usage: 'Замена ВУ, ГИБДД, Госуслуги',
    param: 'trust',
    deltaRange: [0.05, 0.1],
  },
  {
    key: 'docfmt_student_id',
    icon: '🎓',
    name: 'Студенческий / пропуск',
    desc: 'Деловой нейтральный портрет',
    usage: 'ВУЗ, офисный пропуск, корпоративный badge',
    param: 'competence',
    deltaRange: [0.08, 0.15],
  },
  {
    key: 'docfmt_resume_linkedin',
    icon: '💼',
    name: 'Резюме и LinkedIn',
    desc: 'Деловой headshot на светлом фоне',
    usage: 'HeadHunter, LinkedIn, сайт компании',
    param: 'competence',
    deltaRange: [0.1, 0.2],
  },
];

export function isDocumentFormatItem(item: StyleItem): item is DocumentFormatItem {
  return 'usage' in item && typeof (item as DocumentFormatItem).usage === 'string';
}
