export interface StyleItem {
  key: string;
  icon: string;
  name: string;
  desc: string;
  param: 'warmth' | 'presence' | 'appeal' | 'trust' | 'competence' | 'hireability';
  deltaRange: [number, number];
  unlock_after_generations?: number;
}

export interface ScoreParam {
  key: string;
  label: string;
  before: number;
  after: number;
}

export type CategoryId = 'social' | 'cv' | 'dating' | 'model' | 'brand' | 'memes';

export const CATEGORIES: { id: CategoryId; label: string; icon: string }[] = [
  { id: 'social', label: 'Соцсети', icon: '📸' },
  { id: 'cv', label: 'Карьера', icon: '💼' },
  { id: 'dating', label: 'Знакомства', icon: '💕' },
  { id: 'model', label: 'Фотосессия', icon: '📷' },
  { id: 'brand', label: 'Личный бренд', icon: '🔥' },
  { id: 'memes', label: 'Мемы', icon: '😂' },
];

export const COMING_SOON_CATEGORIES: CategoryId[] = ['model', 'brand', 'memes'];

export const PARAMS_BY_MODE: Record<CategoryId, ScoreParam[]> = {
  social: [
    { key: 'social_score', label: 'Social Score', before: 5.99, after: 6.86 },
    { key: 'warmth', label: 'Теплота', before: 6.2, after: 7.1 },
    { key: 'presence', label: 'Уверенность', before: 5.5, after: 6.3 },
    { key: 'appeal', label: 'Привлекательность', before: 6.1, after: 7.0 },
  ],
  cv: [
    { key: 'trust', label: 'Доверие', before: 5.8, after: 6.9 },
    { key: 'competence', label: 'Компетентность', before: 6.0, after: 7.2 },
    { key: 'hireability', label: 'Найм', before: 5.4, after: 6.5 },
    { key: 'presence', label: 'Уверенность', before: 5.7, after: 6.8 },
  ],
  dating: [
    { key: 'dating_score', label: 'Dating Score', before: 5.99, after: 6.86 },
    { key: 'warmth', label: 'Теплота', before: 6.3, after: 7.2 },
    { key: 'presence', label: 'Уверенность', before: 5.6, after: 6.5 },
    { key: 'appeal', label: 'Привлекательность', before: 6.0, after: 7.1 },
  ],
  model: [
    { key: 'warmth', label: 'Теплота', before: 6.1, after: 7.0 },
    { key: 'presence', label: 'Уверенность', before: 5.8, after: 6.7 },
    { key: 'appeal', label: 'Привлекательность', before: 6.3, after: 7.4 },
  ],
  brand: [
    { key: 'trust', label: 'Доверие', before: 5.9, after: 7.0 },
    { key: 'competence', label: 'Компетентность', before: 6.1, after: 7.3 },
    { key: 'presence', label: 'Уверенность', before: 5.7, after: 6.8 },
  ],
  memes: [
    { key: 'warmth', label: 'Теплота', before: 6.4, after: 7.2 },
    { key: 'appeal', label: 'Привлекательность', before: 5.9, after: 6.9 },
    { key: 'presence', label: 'Уверенность', before: 5.5, after: 6.4 },
  ],
};

// Live wizard categories (dating / cv / social) come from
// /api/v1/catalog/styles?schema=v2 — they used to live here as a
// hardcoded array, but the v2 cleanup made the API the single source
// of truth so the admin panel can edit styles without a frontend
// release. Only the still-not-shipped «coming soon» categories remain
// hardcoded; landing-page marketing copy lives in `./landingStyles`.
export const STYLES_BY_CATEGORY: Partial<Record<CategoryId, StyleItem[]>> = {
  model: [
    { key: 'studio_portrait', icon: '📸', name: 'Студийный портрет', desc: 'Классический студийный свет для идеального портфолио', param: 'appeal', deltaRange: [0.55, 0.82] },
    { key: 'fashion_editorial', icon: '👗', name: 'Fashion editorial', desc: 'Высокая мода и стиль для обложки журнала', param: 'appeal', deltaRange: [0.60, 0.88] },
    { key: 'catalog_shoot', icon: '🛍', name: 'Каталог одежды', desc: 'Чистый коммерческий кадр для бренда', param: 'presence', deltaRange: [0.35, 0.55] },
    { key: 'beauty_closeup', icon: '💄', name: 'Beauty крупный план', desc: 'Макро-портрет с акцентом на черты лица', param: 'appeal', deltaRange: [0.50, 0.75] },
    { key: 'street_fashion', icon: '🌆', name: 'Уличная фотосессия', desc: 'Городской фон добавит динамики и стиля', param: 'presence', deltaRange: [0.40, 0.62] },
    { key: 'lookbook', icon: '📖', name: 'Lookbook', desc: 'Минималистичный кадр для подбора образов', param: 'warmth', deltaRange: [0.28, 0.48] },
    { key: 'golden_hour_shoot', icon: '🌅', name: 'Golden hour', desc: 'Золотой свет заката для мягкого портрета', param: 'warmth', deltaRange: [0.45, 0.68] },
    { key: 'avant_garde', icon: '🎭', name: 'Авангард', desc: 'Смелые образы для креативного портфолио', param: 'appeal', deltaRange: [0.52, 0.78] },
  ],
  brand: [
    { key: 'expert_speaker', icon: '🎤', name: 'Эксперт', desc: 'Авторитетный образ для экспертного контента', param: 'competence', deltaRange: [0.50, 0.75] },
    { key: 'visionary', icon: '🔭', name: 'Визионер', desc: 'Вдохновляющий образ лидера мнений', param: 'presence', deltaRange: [0.55, 0.82] },
    { key: 'stage_speaker', icon: '🎙', name: 'Спикер на сцене', desc: 'Динамичный кадр для конференций и выступлений', param: 'presence', deltaRange: [0.60, 0.88] },
    { key: 'desk_work', icon: '💻', name: 'За рабочим столом', desc: 'Рабочий процесс подчеркнёт экспертность', param: 'trust', deltaRange: [0.30, 0.50] },
    { key: 'lifestyle_brand', icon: '☀️', name: 'Lifestyle бренд', desc: 'Стиль жизни как часть личного бренда', param: 'warmth', deltaRange: [0.35, 0.55] },
    { key: 'media_persona', icon: '📺', name: 'Медиа-персона', desc: 'Медийный образ для интервью и шоу', param: 'presence', deltaRange: [0.48, 0.72] },
    { key: 'thought_leader', icon: '💡', name: 'Thought leader', desc: 'Образ мыслителя для премиум-аудитории', param: 'competence', deltaRange: [0.42, 0.65] },
    { key: 'brand_casual', icon: '🤝', name: 'Доступный лидер', desc: 'Открытый и дружелюбный образ бренда', param: 'warmth', deltaRange: [0.38, 0.58] },
  ],
  memes: [
    { key: 'drake_yesno', icon: '🤔', name: 'Drake Yes/No', desc: 'Классика мемов — одобрение и отказ в одном кадре', param: 'warmth', deltaRange: [0.30, 0.50] },
    { key: 'distracted_bf', icon: '👀', name: 'Distracted boyfriend', desc: 'Легендарный мем про отвлечённого парня', param: 'appeal', deltaRange: [0.35, 0.55] },
    { key: 'stonks', icon: '📈', name: 'Stonks', desc: 'Когда инвестиции в образ растут вверх', param: 'presence', deltaRange: [0.40, 0.62] },
    { key: 'this_is_fine', icon: '🔥', name: 'This is fine', desc: 'Спокойствие посреди хаоса — вечный мем', param: 'warmth', deltaRange: [0.25, 0.42] },
    { key: 'gigachad', icon: '💪', name: 'Gigachad', desc: 'Абсолютная уверенность и альфа-энергия', param: 'presence', deltaRange: [0.60, 0.88] },
    { key: 'think_mark', icon: '🧠', name: 'Think Mark', desc: 'Интеллектуальный мем для глубоких мыслей', param: 'appeal', deltaRange: [0.32, 0.52] },
    { key: 'surprised_pika', icon: '😮', name: 'Surprised Pikachu', desc: 'Удивление на лице — универсальная реакция', param: 'warmth', deltaRange: [0.28, 0.46] },
    { key: 'galaxy_brain', icon: '🌌', name: 'Galaxy brain', desc: 'Гениальные решения требуют гениальной подачи', param: 'appeal', deltaRange: [0.45, 0.68] },
  ],
};

export function getMockDelta(range: [number, number], seed?: string): string {
  let hash = 0;
  if (seed) for (let i = 0; i < seed.length; i++) hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0;
  const t = seed ? (Math.abs(hash) % 100) / 100 : 0.5;
  const val = range[0] + t * (range[1] - range[0]);
  return `+ ${val.toFixed(2)}`;
}
