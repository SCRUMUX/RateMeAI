// Hardcoded marketing copy for dating/cv/social styles + scenario items.
// The wizard inside the app fetches the live catalog from
// /api/v1/catalog/styles?schema=v2 (and /scenario-styles for document /
// tinder-pack scenarios), but landing-page sections (hero simulation,
// social-proof feed, review modal, document landing grid) need an
// instant render without waiting for an API round-trip, so we keep a
// frozen mirror here for marketing surfaces only.
//
// IMPORTANT: this list is allowed to drift from `data/styles.json`. It
// is *not* the source of truth — only a local fallback for the public
// homepage. The admin panel (phase 5) updates JSON, not this file.

import type { CategoryId, StyleItem } from './styles';
import { STYLES_BY_CATEGORY } from './styles';

export interface DocumentFormatItem extends StyleItem {
  usage: string;
}

export const DOCUMENT_LANDING_ITEMS: DocumentFormatItem[] = [
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

export const DOCUMENT_USAGE_LOOKUP: Record<string, string> = Object.fromEntries(
  DOCUMENT_LANDING_ITEMS.map((it) => [it.key, it.usage]),
);

export const TINDER_PACK_LANDING_ITEMS: StyleItem[] = [
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

export const LANDING_STYLES_BY_CATEGORY: Partial<Record<CategoryId, StyleItem[]>> = {
  dating: [
    { key: 'paris_eiffel', icon: '🗼', name: 'Эйфелева башня', desc: 'Романтичный кадр у башни подчеркнёт лёгкость и вкус', param: 'appeal', deltaRange: [0.42, 0.68] },
    { key: 'dubai_burj_khalifa', icon: '🏙', name: 'Бурдж-Халифа', desc: 'Амбициозный фон добавит ощущение успеха и масштаба', param: 'presence', deltaRange: [0.55, 0.82] },
    { key: 'nyc_brooklyn_bridge', icon: '🌉', name: 'Бруклинский мост', desc: 'Городская романтика усилит харизму и уверенность', param: 'presence', deltaRange: [0.30, 0.52] },
    { key: 'rome_colosseum', icon: '🏛', name: 'Колизей', desc: 'Величие античности подчеркнёт глубину характера', param: 'presence', deltaRange: [0.35, 0.58] },
    { key: 'venice_san_marco', icon: '🛶', name: 'Венеция', desc: 'Атмосфера каналов создаст ощущение утончённости', param: 'appeal', deltaRange: [0.48, 0.72] },
    { key: 'barcelona_sagrada', icon: '☀️', name: 'Барселона', desc: 'Тёплый свет Барселоны усилит открытость и обаяние', param: 'warmth', deltaRange: [0.38, 0.60] },
    { key: 'london_eye', icon: '🎡', name: 'Лондон', desc: 'Стильный британский фон добавит элегантности', param: 'appeal', deltaRange: [0.18, 0.35] },
    { key: 'tokyo_tower', icon: '🗼', name: 'Токио', desc: 'Японская эстетика подчеркнёт современность и вкус', param: 'appeal', deltaRange: [0.40, 0.62] },
    { key: 'singapore_marina_bay', icon: '🌇', name: 'Сингапур', desc: 'Футуристичный фон усилит впечатление успешности', param: 'presence', deltaRange: [0.52, 0.78] },
    { key: 'sf_golden_gate', icon: '🌁', name: 'Золотые Ворота', desc: 'Калифорнийский свет добавит лёгкости и свободы', param: 'appeal', deltaRange: [0.28, 0.48] },
    { key: 'athens_acropolis', icon: '🏺', name: 'Афины', desc: 'Классическая красота подчеркнёт силу и характер', param: 'presence', deltaRange: [0.32, 0.55] },
    { key: 'sydney_opera', icon: '🎶', name: 'Сидней', desc: 'Яркий фон создаст впечатление открытого человека', param: 'warmth', deltaRange: [0.25, 0.45] },
    { key: 'nyc_times_square', icon: '💡', name: 'Таймс-сквер', desc: 'Энергия мегаполиса подчеркнёт уверенность и драйв', param: 'presence', deltaRange: [0.45, 0.70] },
    { key: 'nyc_central_park', icon: '🌳', name: 'Центральный парк', desc: 'Природа в городе создаст ощущение гармонии', param: 'warmth', deltaRange: [0.22, 0.40] },
    { key: 'london_big_ben', icon: '🕔', name: 'Биг-Бен', desc: 'Классический фон усилит надёжность образа', param: 'presence', deltaRange: [0.15, 0.32] },
    { key: 'airplane_window', icon: '🛫', name: 'У окна самолёта', desc: 'Путешественник — это всегда интригующе и привлекательно', param: 'appeal', deltaRange: [0.20, 0.38] },
    { key: 'hotel_breakfast', icon: '🍳', name: 'Завтрак в отеле', desc: 'Уютный кадр подчеркнёт вкус к жизни', param: 'warmth', deltaRange: [0.12, 0.28] },
    { key: 'sea_balcony', icon: '🌊', name: 'Балкон с видом на море', desc: 'Морской фон усилит спокойствие и притягательность', param: 'appeal', deltaRange: [0.50, 0.75] },
    { key: 'old_town_walk', icon: '🏘', name: 'Старый город', desc: 'Прогулка по улочкам добавит романтичности', param: 'warmth', deltaRange: [0.28, 0.46] },
    { key: 'train_journey', icon: '🚂', name: 'В поезде', desc: 'Динамика поездки подчеркнёт авантюризм и лёгкость', param: 'appeal', deltaRange: [0.10, 0.24] },
    { key: 'street_market', icon: '🛒', name: 'Уличный рынок', desc: 'Живая атмосфера рынка покажет открытость миру', param: 'warmth', deltaRange: [0.18, 0.36] },
    { key: 'hotel_checkin', icon: '🏨', name: 'Лобби отеля', desc: 'Стильный интерьер добавит статуса и ухоженности', param: 'presence', deltaRange: [0.30, 0.50] },
    { key: 'travel_luxury', icon: '💎', name: 'Travel luxury', desc: 'Премиальная обстановка усилит впечатление успеха', param: 'appeal', deltaRange: [0.60, 0.88] },
    { key: 'car_exit', icon: '🚪', name: 'Выход из авто', desc: 'Уверенный жест подчеркнёт стиль и статус', param: 'presence', deltaRange: [0.48, 0.72] },
    { key: 'near_car', icon: '🚗', name: 'У машины', desc: 'Уверенная поза у авто добавит мужественности', param: 'presence', deltaRange: [0.32, 0.52] },
    { key: 'yacht', icon: '⛵', name: 'На яхте', desc: 'Морской кадр создаст ощущение свободы и достатка', param: 'appeal', deltaRange: [0.58, 0.85] },
    { key: 'coffee_date', icon: '🥐', name: 'В кафе', desc: 'Тёплая атмосфера кафе усилит располагающий образ', param: 'warmth', deltaRange: [0.15, 0.30] },
    { key: 'beach_sunset', icon: '🌅', name: 'На закате', desc: 'Золотой свет заката подчеркнёт мягкость и тепло', param: 'warmth', deltaRange: [0.52, 0.78] },
    { key: 'dog_lover', icon: '🐕', name: 'С собакой', desc: 'Фото с питомцем добавит искренности и доверия', param: 'warmth', deltaRange: [0.45, 0.68] },
    { key: 'rooftop_city', icon: '🌃', name: 'На крыше', desc: 'Вид сверху создаст ощущение уверенности и масштаба', param: 'presence', deltaRange: [0.42, 0.65] },
    { key: 'gym_fitness', icon: '💪', name: 'Спортзал', desc: 'Спортивный кадр покажет дисциплину и энергию', param: 'presence', deltaRange: [0.35, 0.55] },
    { key: 'running', icon: '🏃', name: 'Пробежка', desc: 'Динамичная поза подчеркнёт активность и здоровье', param: 'presence', deltaRange: [0.12, 0.26] },
    { key: 'swimming_pool', icon: '🏊', name: 'Бассейн', desc: 'Свежий образ у воды усилит привлекательность', param: 'appeal', deltaRange: [0.38, 0.58] },
    { key: 'hiking', icon: '⛰', name: 'Поход', desc: 'Природный фон покажет характер и выносливость', param: 'presence', deltaRange: [0.22, 0.42] },
    { key: 'yoga_outdoor', icon: '🧘', name: 'Йога', desc: 'Гармоничная поза усилит ощущение внутренней силы', param: 'warmth', deltaRange: [0.28, 0.48] },
    { key: 'cycling', icon: '🚴', name: 'Велопрогулка', desc: 'Активный кадр добавит лёгкости и динамики', param: 'presence', deltaRange: [0.10, 0.22] },
    { key: 'tennis', icon: '🎾', name: 'Теннис', desc: 'Элегантный спорт подчеркнёт стиль и энергичность', param: 'presence', deltaRange: [0.30, 0.50] },
    { key: 'restaurant', icon: '🍷', name: 'Ресторан', desc: 'Ресторанный свет подчеркнёт утончённость и вкус', param: 'appeal', deltaRange: [0.35, 0.55] },
    { key: 'bar_lounge', icon: '🍸', name: 'Бар', desc: 'Приглушённый свет бара добавит загадочности', param: 'appeal', deltaRange: [0.25, 0.42] },
    { key: 'cooking', icon: '👨‍🍳', name: 'На кухне', desc: 'Кулинарный кадр покажет заботу и домашнее тепло', param: 'warmth', deltaRange: [0.20, 0.38] },
    { key: 'rainy_day', icon: '🌧', name: 'В дождь', desc: 'Атмосфера дождя добавит глубины и чувственности', param: 'appeal', deltaRange: [0.15, 0.32] },
    { key: 'night_coffee', icon: '🌙', name: 'Ночной кофе', desc: 'Вечернее настроение создаст интимную атмосферу', param: 'warmth', deltaRange: [0.18, 0.34] },
    { key: 'evening_home', icon: '🏠', name: 'Вечер дома', desc: 'Домашний уют покажет искренность и тепло', param: 'warmth', deltaRange: [0.12, 0.26] },
    { key: 'motorcycle', icon: '🏍', name: 'Мотоцикл', desc: 'Дерзкий образ подчеркнёт смелость и свободу', param: 'presence', deltaRange: [0.50, 0.75] },
    { key: 'in_car', icon: '🚘', name: 'В машине', desc: 'Кадр за рулём добавит уверенности и стиля', param: 'presence', deltaRange: [0.25, 0.42] },
    { key: 'art_gallery', icon: '🎨', name: 'Галерея', desc: 'Культурный фон подчеркнёт интеллект и вкус', param: 'appeal', deltaRange: [0.32, 0.52] },
    { key: 'street_urban', icon: '🏙', name: 'Улица', desc: 'Городская энергия добавит современности образу', param: 'presence', deltaRange: [0.20, 0.38] },
    { key: 'concert', icon: '🎸', name: 'Музыкант', desc: 'Творческий кадр покажет страсть и индивидуальность', param: 'appeal', deltaRange: [0.38, 0.60] },
    { key: 'travel', icon: '✈️', name: 'Аэропорт', desc: 'Образ путешественника подчеркнёт независимость', param: 'appeal', deltaRange: [0.15, 0.30] },
    { key: 'warm_outdoor', icon: '🌤', name: 'На прогулке', desc: 'Естественный свет подчеркнёт натуральность и тепло', param: 'warmth', deltaRange: [0.22, 0.40] },
    { key: 'studio_elegant', icon: '✨', name: 'Студия', desc: 'Студийный свет создаст безупречный портрет', param: 'appeal', deltaRange: [0.62, 0.90] },
    { key: 'cafe', icon: '☕', name: 'Кафе / бар', desc: 'Расслабленная обстановка покажет лёгкость в общении', param: 'warmth', deltaRange: [0.18, 0.35] },
    ...TINDER_PACK_LANDING_ITEMS,
  ],
  cv: [
    { key: 'corporate', icon: '🏢', name: 'Корпоративный', desc: 'Деловой фон усилит впечатление надёжности', param: 'presence', deltaRange: [0.35, 0.55] },
    { key: 'boardroom', icon: '📋', name: 'Переговорная', desc: 'Переговорная покажет лидерские качества', param: 'presence', deltaRange: [0.55, 0.80] },
    { key: 'formal_portrait', icon: '📷', name: 'Формальный портрет', desc: 'Классический портрет повысит доверие с первого взгляда', param: 'presence', deltaRange: [0.45, 0.68] },
    { key: 'glass_wall_pose', icon: '🏢', name: 'У стеклянной стены', desc: 'Современный офис подчеркнёт прогрессивность', param: 'presence', deltaRange: [0.30, 0.50] },
    { key: 'startup_casual', icon: '🚀', name: 'Стартап', desc: 'Непринуждённый стиль покажет гибкость и инновационность', param: 'warmth', deltaRange: [0.28, 0.48] },
    { key: 'coworking', icon: '👥', name: 'Коворкинг', desc: 'Открытое пространство усилит командный дух', param: 'warmth', deltaRange: [0.15, 0.32] },
    { key: 'video_call', icon: '📹', name: 'Созвон', desc: 'Идеальный кадр для профессиональных созвонов', param: 'presence', deltaRange: [0.12, 0.28] },
    { key: 'analytics_review', icon: '📊', name: 'Аналитика', desc: 'Аналитический фокус подчеркнёт экспертность', param: 'presence', deltaRange: [0.32, 0.52] },
    { key: 'notebook_ideas', icon: '📝', name: 'Запись идей', desc: 'Рабочий момент покажет вдумчивость и глубину', param: 'warmth', deltaRange: [0.10, 0.24] },
    { key: 'tablet_stylus', icon: '📱', name: 'Планшет', desc: 'Технологичный образ подчеркнёт современность', param: 'presence', deltaRange: [0.18, 0.35] },
    { key: 'coffee_break_work', icon: '☕', name: 'Перерыв с кофе', desc: 'Рабочий перерыв покажет человечность и баланс', param: 'warmth', deltaRange: [0.15, 0.30] },
    { key: 'late_hustle', icon: '🌙', name: 'Вечерняя работа', desc: 'Вечерний кадр подчеркнёт целеустремлённость', param: 'presence', deltaRange: [0.25, 0.42] },
    { key: 'before_meeting', icon: '💼', name: 'Перед встречей', desc: 'Сосредоточенность перед встречей усилит серьёзность', param: 'presence', deltaRange: [0.28, 0.46] },
    { key: 'between_meetings', icon: '📲', name: 'Между встречами', desc: 'Динамичный ритм покажет востребованность', param: 'presence', deltaRange: [0.12, 0.26] },
    { key: 'decision_moment', icon: '🏙', name: 'Момент решения', desc: 'Уверенный взгляд подчеркнёт решительность', param: 'presence', deltaRange: [0.48, 0.72] },
    { key: 'business_lounge', icon: '✈️', name: 'Бизнес-лаунж', desc: 'Премиальный фон усилит восприятие статуса', param: 'presence', deltaRange: [0.52, 0.78] },
    { key: 'speaker_stage', icon: '🎤', name: 'Спикер', desc: 'Сцена подчеркнёт авторитет и экспертность', param: 'presence', deltaRange: [0.60, 0.88] },
    { key: 'standing_desk', icon: '🖥', name: 'Домашний офис', desc: 'Современный формат покажет адаптивность', param: 'warmth', deltaRange: [0.10, 0.22] },
    { key: 'digital_nomad', icon: '🌐', name: 'Digital nomad', desc: 'Свободный стиль работы подчеркнёт независимость', param: 'appeal', deltaRange: [0.35, 0.55] },
    { key: 'quiet_expert', icon: '📚', name: 'Тихий эксперт', desc: 'Спокойная уверенность усилит доверие к экспертизе', param: 'warmth', deltaRange: [0.22, 0.40] },
    { key: 'intellectual', icon: '🎓', name: 'Интеллектуал', desc: 'Интеллектуальный образ подчеркнёт глубину знаний', param: 'warmth', deltaRange: [0.28, 0.48] },
    { key: 'entrepreneur_on_move', icon: '🌱', name: 'Предприниматель', desc: 'Динамика действия покажет предпринимательский дух', param: 'presence', deltaRange: [0.50, 0.75] },
    { key: 'man_with_mission', icon: '🎯', name: 'Человек с миссией', desc: 'Целеустремлённость подчеркнёт лидерский потенциал', param: 'presence', deltaRange: [0.55, 0.82] },
    { key: 'tech_developer', icon: '💻', name: 'IT разработчик', desc: 'Техническая среда усилит восприятие компетентности', param: 'presence', deltaRange: [0.25, 0.42] },
    { key: 'creative_director', icon: '🎨', name: 'Креативный директор', desc: 'Творческий фон покажет нестандартное мышление', param: 'appeal', deltaRange: [0.40, 0.62] },
    { key: 'medical', icon: '🏥', name: 'Медицина', desc: 'Профессиональный фон усилит доверие пациентов', param: 'warmth', deltaRange: [0.38, 0.58] },
    { key: 'legal_finance', icon: '⚖️', name: 'Юрист / Финансы', desc: 'Строгий стиль подчеркнёт надёжность и точность', param: 'presence', deltaRange: [0.42, 0.65] },
    { key: 'architect', icon: '📐', name: 'Архитектор', desc: 'Пространственный фон покажет визуальное мышление', param: 'appeal', deltaRange: [0.32, 0.52] },
    { key: 'podcast', icon: '🎧', name: 'Подкастер', desc: 'Медиа-формат подчеркнёт коммуникабельность', param: 'warmth', deltaRange: [0.30, 0.48] },
    { key: 'mentor', icon: '🤝', name: 'Ментор', desc: 'Открытая поза покажет готовность помогать другим', param: 'warmth', deltaRange: [0.45, 0.68] },
    { key: 'outdoor_business', icon: '☀️', name: 'Бизнес на террасе', desc: 'Свежий воздух подчеркнёт баланс и стиль жизни', param: 'warmth', deltaRange: [0.20, 0.38] },
    { key: 'creative', icon: '🎨', name: 'Креативный', desc: 'Творческий подход покажет оригинальность мышления', param: 'appeal', deltaRange: [0.35, 0.55] },
    { key: 'neutral', icon: '🎯', name: 'Нейтральный фон', desc: 'Чистый фон сфокусирует внимание на личности', param: 'presence', deltaRange: [0.08, 0.20] },
  ],
  social: [
    { key: 'mirror_aesthetic', icon: '🪩', name: 'У зеркала', desc: 'Зеркальный кадр добавит стиля и уверенности', param: 'appeal', deltaRange: [0.30, 0.50] },
    { key: 'elevator_clean', icon: '🛗', name: 'В лифте', desc: 'Чистый минималистичный кадр привлечёт внимание', param: 'appeal', deltaRange: [0.12, 0.26] },
    { key: 'candid_street', icon: '📸', name: 'Случайный кадр', desc: 'Естественность подчеркнёт искренность и живость', param: 'warmth', deltaRange: [0.22, 0.40] },
    { key: 'book_and_coffee', icon: '📖', name: 'Книга и кофе', desc: 'Уютная атмосфера создаст вовлекающий контент', param: 'warmth', deltaRange: [0.18, 0.35] },
    { key: 'shopfront', icon: '🛍', name: 'У витрины', desc: 'Городской фон усилит стильность образа', param: 'appeal', deltaRange: [0.25, 0.42] },
    { key: 'focused_mood', icon: '👀', name: 'Фокус', desc: 'Сфокусированный взгляд притянет внимание зрителей', param: 'presence', deltaRange: [0.32, 0.52] },
    { key: 'influencer_urban', icon: '🌃', name: 'Urban блогер', desc: 'Городская эстетика усилит трендовый образ', param: 'appeal', deltaRange: [0.38, 0.58] },
    { key: 'influencer_luxury', icon: '💎', name: 'Luxury', desc: 'Премиум-обстановка создаст вау-эффект в ленте', param: 'appeal', deltaRange: [0.58, 0.85] },
    { key: 'influencer_minimal', icon: '⚪', name: 'Минимализм', desc: 'Чистый стиль подчеркнёт вкус и современность', param: 'appeal', deltaRange: [0.20, 0.38] },
    { key: 'golden_hour', icon: '🌟', name: 'Golden hour', desc: 'Золотой свет сделает кадр тёплым и запоминающимся', param: 'appeal', deltaRange: [0.52, 0.78] },
    { key: 'neon_night', icon: '💠', name: 'Неон', desc: 'Неоновый свет создаст яркий цепляющий контент', param: 'appeal', deltaRange: [0.45, 0.70] },
    { key: 'tinder_top', icon: '🔥', name: 'Для Tinder', desc: 'Максимальная привлекательность для анкеты', param: 'appeal', deltaRange: [0.55, 0.82] },
    { key: 'reading_home', icon: '📚', name: 'Чтение дома', desc: 'Домашний кадр покажет глубину и интеллект', param: 'warmth', deltaRange: [0.15, 0.30] },
    { key: 'reading_cafe', icon: '☕', name: 'Чтение в кафе', desc: 'Атмосфера кафе добавит стиля к увлечению', param: 'warmth', deltaRange: [0.18, 0.34] },
    { key: 'sketching', icon: '✏️', name: 'Скетчинг', desc: 'Творческий момент покажет талант и индивидуальность', param: 'warmth', deltaRange: [0.10, 0.24] },
    { key: 'photographer', icon: '📷', name: 'Фотограф', desc: 'Камера в руках подчеркнёт творческий взгляд', param: 'appeal', deltaRange: [0.28, 0.48] },
    { key: 'meditation', icon: '🧘', name: 'Медитация', desc: 'Гармоничный кадр усилит ощущение внутренней силы', param: 'warmth', deltaRange: [0.22, 0.40] },
    { key: 'online_learning', icon: '💻', name: 'Обучение', desc: 'Образовательный контент подчеркнёт развитие', param: 'warmth', deltaRange: [0.08, 0.20] },
    { key: 'yoga_social', icon: '🪷', name: 'Йога', desc: 'Спокойная сила привлечёт осознанную аудиторию', param: 'warmth', deltaRange: [0.25, 0.42] },
    { key: 'cycling_social', icon: '🚴', name: 'Велопрогулка', desc: 'Активный образ жизни вдохновит подписчиков', param: 'presence', deltaRange: [0.15, 0.32] },
    { key: 'fitness_lifestyle', icon: '💪', name: 'Фитнес', desc: 'Спортивный кадр покажет дисциплину и энергию', param: 'presence', deltaRange: [0.35, 0.55] },
    { key: 'panoramic_window', icon: '🌃', name: 'Панорамное окно', desc: 'Вид из окна создаст кинематографичный контент', param: 'appeal', deltaRange: [0.40, 0.62] },
    { key: 'in_motion', icon: '🏃', name: 'В движении', desc: 'Динамика кадра передаст энергию и драйв', param: 'presence', deltaRange: [0.20, 0.38] },
    { key: 'creative_insight', icon: '💡', name: 'Креативный инсайт', desc: 'Момент вдохновения подчеркнёт креативность', param: 'appeal', deltaRange: [0.12, 0.28] },
    { key: 'architecture_shadow', icon: '🏛', name: 'Тень архитектуры', desc: 'Архитектурный свет добавит глубины и арта', param: 'appeal', deltaRange: [0.35, 0.55] },
    { key: 'achievement_moment', icon: '🏆', name: 'Момент победы', desc: 'Триумфальный кадр вызовет восхищение аудитории', param: 'presence', deltaRange: [0.50, 0.75] },
    { key: 'light_irony', icon: '😏', name: 'Лёгкая ирония', desc: 'Ироничный образ покажет чувство юмора и стиль', param: 'warmth', deltaRange: [0.28, 0.46] },
    { key: 'skyscraper_view', icon: '🌇', name: 'Вид с небоскрёба', desc: 'Панорамный фон создаст ощущение достижений', param: 'presence', deltaRange: [0.48, 0.72] },
    { key: 'after_work', icon: '🌆', name: 'После работы', desc: 'Вечерний свет добавит атмосферности контенту', param: 'warmth', deltaRange: [0.18, 0.35] },
    { key: 'evening_planning', icon: '📝', name: 'Вечернее планирование', desc: 'Рабочий вечер подчеркнёт серьёзность намерений', param: 'presence', deltaRange: [0.10, 0.24] },
    { key: 'dark_moody', icon: '🌑', name: 'Dark moody', desc: 'Контрастный стиль создаст запоминающийся образ', param: 'appeal', deltaRange: [0.42, 0.65] },
    { key: 'vintage_film', icon: '🎞', name: 'Винтаж', desc: 'Ретро-обработка добавит уникальности и ностальгии', param: 'appeal', deltaRange: [0.30, 0.50] },
    { key: 'pastel_soft', icon: '🌸', name: 'Пастель', desc: 'Мягкие тона создадут нежный эстетичный контент', param: 'warmth', deltaRange: [0.25, 0.42] },
    { key: 'instagram_aesthetic', icon: '📸', name: 'Instagram', desc: 'Идеальная эстетика для Instagram-ленты', param: 'appeal', deltaRange: [0.42, 0.65] },
    { key: 'youtube_creator', icon: '🎬', name: 'YouTube', desc: 'Динамичный кадр усилит узнаваемость канала', param: 'presence', deltaRange: [0.38, 0.58] },
    { key: 'linkedin_premium', icon: '💼', name: 'LinkedIn', desc: 'Профессиональный кадр повысит доверие коллег', param: 'presence', deltaRange: [0.32, 0.52] },
    { key: 'podcast_host', icon: '🎧', name: 'Подкаст', desc: 'Медийный образ подчеркнёт экспертность и голос', param: 'warmth', deltaRange: [0.28, 0.46] },
    { key: 'creative_portrait', icon: '🎨', name: 'Арт-портрет', desc: 'Художественный подход выделит из массы контента', param: 'appeal', deltaRange: [0.55, 0.80] },
    { key: 'morning_routine', icon: '🌅', name: 'Утро', desc: 'Утренний свет создаст свежий и энергичный образ', param: 'warmth', deltaRange: [0.20, 0.38] },
    { key: 'food_blogger', icon: '🍽', name: 'Фуд-блогер', desc: 'Гастрономический кадр покажет стиль жизни', param: 'warmth', deltaRange: [0.15, 0.32] },
    { key: 'travel_blogger', icon: '✈️', name: 'Тревел-блогер', desc: 'Путешествия вдохновят и привлекут аудиторию', param: 'appeal', deltaRange: [0.35, 0.55] },
    { key: 'influencer', icon: '🌟', name: 'Influencer', desc: 'Инфлюенсерский стиль усилит вовлечённость', param: 'appeal', deltaRange: [0.45, 0.68] },
    { key: 'luxury', icon: '💎', name: 'Luxury classic', desc: 'Премиальный образ создаст эффект роскоши', param: 'appeal', deltaRange: [0.60, 0.88] },
    { key: 'casual', icon: '☀️', name: 'Casual', desc: 'Лёгкий стиль подчеркнёт естественность и вкус', param: 'warmth', deltaRange: [0.12, 0.26] },
    { key: 'artistic', icon: '🎨', name: 'Artistic', desc: 'Арт-стиль покажет креативность и уникальный взгляд', param: 'appeal', deltaRange: [0.48, 0.72] },
  ],
};

// Convenience export for landing surfaces that need a complete map across all
// 6 categories (Simulation, ReviewModal, social-proof feed). Coming-soon
// categories (model/brand/memes) are reused from the main hardcode; live
// categories (dating/cv/social) come from the frozen marketing copy above.
export const FULL_LANDING_STYLES_BY_CATEGORY: Record<CategoryId, StyleItem[]> = {
  dating: LANDING_STYLES_BY_CATEGORY.dating ?? [],
  cv: LANDING_STYLES_BY_CATEGORY.cv ?? [],
  social: LANDING_STYLES_BY_CATEGORY.social ?? [],
  model: STYLES_BY_CATEGORY.model ?? [],
  brand: STYLES_BY_CATEGORY.brand ?? [],
  memes: STYLES_BY_CATEGORY.memes ?? [],
};
