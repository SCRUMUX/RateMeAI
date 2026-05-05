import type { CategoryId } from './styles';

export type TestimonialTier = 'Обычный' | 'Премиум';

/**
 * Review surface category. The main carousel & scenario landings use
 * `CategoryId`, but the documents landing has its own pseudo-category
 * outside of `CATEGORIES` (no tab, no wizard) and only owns its own
 * style showcase + review pool.
 */
export type ReviewCategory = CategoryId | 'documents';

/**
 * Where the testimonial is allowed to appear:
 *  - `carousel`: главная карусель `Testimonials` (1 на стиль не нужно
 *     — берём 4-5 ярких отзывов на категорию).
 *  - `style-showcase`: отзывы под слайдером в Simulation, по одному
 *     на каждый стиль; не пересекаются с карусельными по тексту.
 */
export type TestimonialUsage = 'carousel' | 'style-showcase';

export interface Testimonial {
  id: string;
  styleKey: string;
  category: ReviewCategory;
  nickname: string;
  /** Plain short review (kept for legacy `Simulation` block). */
  shortReview: string;
  /** Long-form review for the modal. */
  fullReview: string;
  /**
   * Compact review with Telegram-style unicode emoji used by the
   * carousel cards in `Testimonials`. Falls back to `shortReview`
   * when missing.
   */
  emojiReview?: string;
  beforeScore: number;
  afterScore: number;
  deltaRange: [number, number];
  /**
   * DiceBear seed (defaults to nickname without `@`). Lets us swap
   * the avatar deterministically without touching the API URL in
   * the component.
   */
  avatarSeed?: string;
  /** Generation tier shown as a badge next to the direction chip. */
  tier?: TestimonialTier;
  /** Where this entry is shown. Defaults to `carousel`. */
  usage?: TestimonialUsage;
}

export const TESTIMONIALS: Testimonial[] = [
  // --- Social ---
  {
    id: 'social-1',
    styleKey: 'mirror_aesthetic',
    category: 'social',
    nickname: '@marina_design',
    shortReview: 'Подписчики сразу заметили разницу — лайков стало в 3 раза больше!',
    fullReview: 'Загрузила своё обычное селфи и выбрала стиль «У зеркала». Результат поразил — фото стало выглядеть как после профессиональной съёмки. Подписчики сразу заметили разницу, лайков стало в 3 раза больше. Теперь использую для каждого поста.',
    emojiReview: 'Подписчики реально заметили разницу 🤯 лайков стало в 3 раза больше 🔥 теперь юзаю на каждый пост 💅',
    beforeScore: 5.82,
    afterScore: 6.71,
    deltaRange: [0.25, 0.45],
    tier: 'Премиум',
  },
  {
    id: 'social-2',
    styleKey: 'golden_hour',
    category: 'social',
    nickname: '@alex_photo',
    shortReview: 'Golden hour эффект — именно то, чего не хватало моим фото',
    fullReview: 'Всегда завидовал блогерам с идеальным светом на фотках. Стиль Golden hour дал мне именно тот тёплый свет, который раньше получался только на закате. Engagement rate вырос на 40%, а я просто загрузил обычное фото из дома.',
    emojiReview: 'Тёплый свет 🌅 ровно как у блогеров, engagement +40% 📈 а я просто загрузил селфи из дома 🤝',
    beforeScore: 5.44,
    afterScore: 6.58,
    deltaRange: [0.35, 0.55],
    tier: 'Обычный',
  },
  {
    id: 'social-3',
    styleKey: 'influencer_urban',
    category: 'social',
    nickname: '@kate_lifestyle',
    shortReview: 'Мой Instagram наконец выглядит как у топ-блогеров',
    fullReview: 'Я веду lifestyle-блог и мне всегда не хватало «того самого» визуала. Urban блогер стиль превратил мои обычные уличные фото в контент уровня журнала. Три последних поста залетели в рекомендации. Это реально работает.',
    emojiReview: 'Lifestyle-блог наконец выглядит как у топов 💎 три поста залетели в рекомендации 🚀',
    beforeScore: 6.01,
    afterScore: 7.12,
    deltaRange: [0.25, 0.45],
    tier: 'Премиум',
  },
  {
    id: 'social-4',
    styleKey: 'neon_night',
    category: 'social',
    nickname: '@dmitry_beats',
    shortReview: 'Неоновый стиль идеально зашёл для моей музыкальной страницы',
    fullReview: 'Я продвигаю свою музыку в соцсетях и неоновый стиль оказался идеальным для моего бренда. Каждый пост получает на 50% больше сохранений. Фото выглядят как кадры из клипа, а я потратил 30 секунд.',
    emojiReview: 'Неон идеально под мой музыкальный бренд 🎧 +50% сохранений на пост 💾 кадры будто из клипа 🎬',
    beforeScore: 5.67,
    afterScore: 6.89,
    deltaRange: [0.35, 0.55],
    tier: 'Обычный',
  },
  {
    id: 'social-5',
    styleKey: 'candid_street',
    category: 'social',
    nickname: '@anya_moments',
    shortReview: 'Случайные кадры стали выглядеть как спланированная съёмка',
    fullReview: 'Раньше мои «случайные» фото выглядели именно как случайные — без стиля и атмосферы. Теперь каждый кадр с улицы превращается в эстетичный контент. Друзья думают, что я наняла фотографа. Очень довольна результатом!',
    emojiReview: 'Случайные кадры теперь как со съёмки 🎞️ друзья думают, что я наняла фотографа 😅',
    beforeScore: 5.33,
    afterScore: 6.42,
    deltaRange: [0.25, 0.45],
    tier: 'Обычный',
  },

  // --- CV ---
  {
    id: 'cv-1',
    styleKey: 'corporate',
    category: 'cv',
    nickname: '@sergey_pm',
    shortReview: 'HR написала, что моё фото на LinkedIn произвело сильное впечатление',
    fullReview: 'Обновил фото на LinkedIn с помощью корпоративного стиля. Через неделю получил 3 приглашения на собеседования. HR одной компании отдельно отметила, что моё фото выглядит очень профессионально. Инвестиция в 1 кредит окупилась многократно.',
    emojiReview: 'Обновил фото на LinkedIn 💼 за неделю 3 приглашения на собес ✉️ HR отдельно отметила фото 👌',
    beforeScore: 5.71,
    afterScore: 6.93,
    deltaRange: [0.25, 0.45],
    tier: 'Премиум',
  },
  {
    id: 'cv-2',
    styleKey: 'speaker_stage',
    category: 'cv',
    nickname: '@elena_ceo',
    shortReview: 'Стиль «Спикер» добавил авторитетности моему профилю',
    fullReview: 'Как основатель стартапа мне важно выглядеть уверенно. Стиль «Спикер» создал ощущение, что я выступаю на крупной конференции. Инвесторы стали воспринимать меня серьёзнее — и это видно по конверсии моих питчей.',
    emojiReview: 'Стиль «Спикер» добавил авторитета 🎤 инвесторы стали слушать серьёзнее, конверсия питчей выросла 📈',
    beforeScore: 5.88,
    afterScore: 7.14,
    deltaRange: [0.35, 0.55],
    tier: 'Премиум',
  },
  {
    id: 'cv-3',
    styleKey: 'tech_developer',
    category: 'cv',
    nickname: '@max_dev',
    shortReview: 'Наконец-то нормальное фото для GitHub и резюме',
    fullReview: 'Как разработчику мне всегда было лень делать нормальное фото для профиля. IT-стиль сделал из моего домашнего селфи профессиональный портрет. Поставил на GitHub, LinkedIn и резюме — отклики выросли вдвое.',
    emojiReview: 'Из домашнего селфи получился норм портрет 👨‍💻 поставил на GitHub и резюме — отклики x2 ⚡',
    beforeScore: 5.22,
    afterScore: 6.45,
    deltaRange: [0.25, 0.45],
    tier: 'Обычный',
  },
  {
    id: 'cv-4',
    styleKey: 'startup_casual',
    category: 'cv',
    nickname: '@liza_product',
    shortReview: 'Стартап-стиль — ровно между формальным и дружелюбным',
    fullReview: 'Работаю продакт-менеджером и классический костюм — не мой стиль. «Стартап» попал в точку: выгляжу профессионально, но без лишней формальности. Идеально для IT-компаний. Коллеги спрашивают, где я делала фото.',
    emojiReview: 'Между формальным и дружелюбным — идеально 🙌 коллеги спрашивают, где я делала фото 📸',
    beforeScore: 5.95,
    afterScore: 6.88,
    deltaRange: [0.25, 0.45],
    tier: 'Обычный',
  },
  {
    id: 'cv-5',
    styleKey: 'mentor',
    category: 'cv',
    nickname: '@igor_coach',
    shortReview: 'Клиенты стали записываться чаще — фото внушает доверие',
    fullReview: 'Я бизнес-коуч, и мне важно выглядеть открытым, но компетентным. Стиль «Ментор» идеально передал этот баланс. После смены фото на сайте количество записей на консультации выросло на 25%. Рекомендую всем, кто работает с людьми.',
    emojiReview: 'Открытый, но экспертный 🤝 после смены фото записей на консультации +25% 📅',
    beforeScore: 5.64,
    afterScore: 6.97,
    deltaRange: [0.35, 0.55],
    tier: 'Премиум',
  },

  // --- Dating ---
  {
    id: 'dating-1',
    styleKey: 'paris_eiffel',
    category: 'dating',
    nickname: '@natasha_travel',
    shortReview: 'Мэтчей стало в 5 раз больше — фото у башни работает магически',
    fullReview: 'Загрузила своё обычное фото и выбрала Эйфелеву башню. Результат — как будто я реально там побывала с профессиональным фотографом. За первую неделю мэтчей стало в 5 раз больше. Парни пишут первыми и спрашивают про Париж.',
    emojiReview: 'Загрузила обычное фото — выбрала Эйфелеву 🗼 мэтчей в 5 раз больше 💌 пишут первыми и спрашивают про Париж',
    beforeScore: 5.91,
    afterScore: 7.05,
    deltaRange: [0.25, 0.45],
    tier: 'Премиум',
  },
  {
    id: 'dating-2',
    styleKey: 'coffee_date',
    category: 'dating',
    nickname: '@andrey_msk',
    shortReview: 'Фото в кафе сделало профиль намного теплее и привлекательнее',
    fullReview: 'Мой друг посоветовал сервис после того как сам нашёл девушку в Tinder. Стиль «В кафе» превратил скучный портрет в уютное фото, от которого хочется познакомиться. Количество лайков удвоилось за пару дней.',
    emojiReview: 'Стиль «В кафе» сделал профиль теплее ☕ лайков x2 за пару дней 💛',
    beforeScore: 5.55,
    afterScore: 6.68,
    deltaRange: [0.25, 0.45],
    tier: 'Обычный',
  },
  {
    id: 'dating-3',
    styleKey: 'dog_lover',
    category: 'dating',
    nickname: '@olga_sunny',
    shortReview: 'Фото с собакой — лучшее решение для dating-профиля!',
    fullReview: 'У меня нет собаки, но фото с ней получилось настолько естественным! Девочки в приложении знакомств реагируют невероятно тепло. Это фото стало моим главным в профиле. Искренность и тепло — именно то, что нужно для первого впечатления.',
    emojiReview: 'Собаки у меня нет, но фото получилось настоящим 🐕 девочки реагируют невероятно тепло ✨',
    beforeScore: 5.78,
    afterScore: 7.01,
    deltaRange: [0.35, 0.55],
    tier: 'Премиум',
  },
  {
    id: 'dating-4',
    styleKey: 'beach_sunset',
    category: 'dating',
    nickname: '@vika_sea',
    shortReview: 'Закатное фото добавило романтики — переписки стали длиннее',
    fullReview: 'Выбрала стиль «На закате» и не пожалела. Золотой свет сделал фото невероятно мягким и притягательным. Заметила, что люди стали писать более длинные и вдумчивые первые сообщения. Атмосфера фото задаёт тон общению.',
    emojiReview: 'Закатный свет 🌇 фото мягкое, переписки сразу длиннее и вдумчивее 💬',
    beforeScore: 6.10,
    afterScore: 7.22,
    deltaRange: [0.35, 0.55],
    tier: 'Обычный',
  },
  {
    id: 'dating-5',
    styleKey: 'rooftop_city',
    category: 'dating',
    nickname: '@mark_night',
    shortReview: 'Вид с крыши + уверенный взгляд = идеальное фото для анкеты',
    fullReview: 'Стиль «На крыше» добавил моему профилю ощущение успешности и уверенности. Фото выглядит дорого и стильно, при этом естественно. Получил больше 50 мэтчей за первую неделю. Лучшая инвестиция в dating-профиль.',
    emojiReview: 'Крыша + уверенный взгляд 🌃 +50 мэтчей за неделю 🎯 лучшая инвестиция в анкету 💯',
    beforeScore: 5.42,
    afterScore: 6.79,
    deltaRange: [0.35, 0.55],
    tier: 'Премиум',
  },

  // --- Style-showcase reviews (under the slider in Simulation).
  // Не пересекаются по тексту с carousel-отзывами выше — короче,
  // одна-две строки с эмодзи, привязаны к конкретному styleKey. ---

  // Social ---
  { id: 'ss-social-vintage', category: 'social', styleKey: 'vintage_film', nickname: '@artem_shoot', shortReview: 'Винтаж дал фото характер 🎞️ постом загорелась лента 🔥', fullReview: 'Винтаж дал фото характер. Постом загорелась лента — друзья спрашивают, какой пресет.', emojiReview: 'Винтаж дал характер 🎞️ лента загорелась 🔥', beforeScore: 5.7, afterScore: 6.7, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-social-luxury', category: 'social', styleKey: 'influencer_luxury', nickname: '@dasha_glow', shortReview: 'Luxury-стиль вытащил фото на новый уровень 💎', fullReview: 'Luxury-стиль вытащил фото на новый уровень — выглядит, будто снимал бренд.', emojiReview: 'Luxury вытащил фото на уровень 💎 будто снимал бренд ✨', beforeScore: 5.9, afterScore: 7.1, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-social-tinder-top', category: 'social', styleKey: 'tinder_top', nickname: '@nik_solo', shortReview: 'Tinder-стиль — лайки реально полетели 🔥', fullReview: 'Tinder-стиль — лайки реально полетели. Профиль ожил за вечер.', emojiReview: 'Tinder-стиль 🔥 лайки полетели, профиль ожил за вечер ⚡', beforeScore: 5.5, afterScore: 6.7, deltaRange: [0.4, 0.6], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-social-pastel', category: 'social', styleKey: 'pastel_soft', nickname: '@lena_pastel', shortReview: 'Пастельные тона сделали ленту мягкой и эстетичной 🌸', fullReview: 'Пастельные тона сделали ленту мягкой — фид наконец смотрится цельно.', emojiReview: 'Мягкая пастель 🌸 фид смотрится цельно 💗', beforeScore: 5.6, afterScore: 6.6, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-social-yt', category: 'social', styleKey: 'youtube_creator', nickname: '@vlad_yt', shortReview: 'Аватарка канала наконец заиграла 🎬', fullReview: 'Аватарка канала наконец заиграла — узнаваемость пошла вверх.', emojiReview: 'Аватарка канала заиграла 🎬 узнаваемость +', beforeScore: 5.5, afterScore: 6.6, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-social-dark', category: 'social', styleKey: 'dark_moody', nickname: '@ksu_noir', shortReview: 'Dark moody — про меня и мой саунд 🌑', fullReview: 'Dark moody — про меня и мой саунд. Фото будто плакат к релизу.', emojiReview: 'Dark moody 🌑 фото как плакат к релизу 🎧', beforeScore: 5.7, afterScore: 6.9, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-social-instagram', category: 'social', styleKey: 'instagram_aesthetic', nickname: '@sofi_ig', shortReview: 'Идеальный кадр для ленты — без обработок 📸', fullReview: 'Идеальный кадр для ленты — даже править не пришлось.', emojiReview: 'Кадр для ленты 📸 править не пришлось ✨', beforeScore: 5.6, afterScore: 6.7, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-social-fitness', category: 'social', styleKey: 'fitness_lifestyle', nickname: '@max_strong', shortReview: 'Спортивный кадр без зеркальной банальности 💪', fullReview: 'Спортивный кадр без зеркальной банальности — выглядит как съёмка для бренда.', emojiReview: 'Спорт без зеркала 💪 как съёмка для бренда 🏋️', beforeScore: 5.7, afterScore: 6.8, deltaRange: [0.3, 0.5], tier: 'Премиум', usage: 'style-showcase' },

  // CV ---
  { id: 'ss-cv-boardroom', category: 'cv', styleKey: 'boardroom', nickname: '@ivan_lead', shortReview: 'Переговорная — фото будто после интервью в Forbes 📋', fullReview: 'Переговорная — фото будто после интервью в Forbes. Hr пишут первыми.', emojiReview: 'Будто после интервью в Forbes 📋 HR пишут первыми ✉️', beforeScore: 5.8, afterScore: 7.0, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-cv-formal', category: 'cv', styleKey: 'formal_portrait', nickname: '@anna_hr', shortReview: 'Классический портрет — собес назначили в день отправки 💼', fullReview: 'Классический портрет — собес назначили в тот же день, когда отправила резюме.', emojiReview: 'Классический портрет 💼 собес в тот же день 📅', beforeScore: 5.7, afterScore: 6.9, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-cv-mission', category: 'cv', styleKey: 'man_with_mission', nickname: '@oleg_drive', shortReview: 'Фото с миссией — взгляд решает всё 🎯', fullReview: 'Фото с миссией — взгляд решает всё. Питч стал звучать иначе.', emojiReview: 'Взгляд решает всё 🎯 питч звучит иначе 🚀', beforeScore: 5.9, afterScore: 7.2, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-cv-creative-dir', category: 'cv', styleKey: 'creative_director', nickname: '@vera_art', shortReview: 'Креативный директор — портрет с характером 🎨', fullReview: 'Креативный директор — портрет с характером, идеально для портфолио.', emojiReview: 'Креатив-директор 🎨 портрет с характером ✨', beforeScore: 5.8, afterScore: 7.0, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-cv-medical', category: 'cv', styleKey: 'medical', nickname: '@dr_petrov', shortReview: 'Доверие с первого взгляда — пациенты заметили 🏥', fullReview: 'Доверие с первого взгляда — пациенты заметили обновление профиля.', emojiReview: 'Доверие с первого взгляда 🏥 пациенты заметили 👌', beforeScore: 5.6, afterScore: 6.8, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-cv-legal', category: 'cv', styleKey: 'legal_finance', nickname: '@kira_law', shortReview: 'Юрист — строго, точно, в стиле Big4 ⚖️', fullReview: 'Юрист — строго, точно, в стиле Big4. Профиль выглядит, как выпускник МГИМО.', emojiReview: 'Big4 уровень ⚖️ строго и точно 🎓', beforeScore: 5.8, afterScore: 7.0, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-cv-architect', category: 'cv', styleKey: 'architect', nickname: '@misha_arch', shortReview: 'Архитектор — пространство в кадре говорит само за себя 📐', fullReview: 'Архитектор — пространство в кадре работает на образ. Заказчики стали приходить с готовой задачей.', emojiReview: 'Пространство в кадре 📐 заказчики приходят сразу с задачей 🏛', beforeScore: 5.7, afterScore: 6.9, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-cv-podcast', category: 'cv', styleKey: 'podcast', nickname: '@artur_voice', shortReview: 'Подкастер — стиль для медиа-персоны 🎧', fullReview: 'Подкастер — стиль для медиа-персоны. Послушать стало хочется ещё до клика.', emojiReview: 'Стиль для медиа-персоны 🎧 хочется послушать ещё до клика 🎙', beforeScore: 5.6, afterScore: 6.7, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-cv-entrepreneur', category: 'cv', styleKey: 'entrepreneur_on_move', nickname: '@gleb_founder', shortReview: 'Предприниматель в движении — драйв в каждом кадре 🌱', fullReview: 'Предприниматель в движении — драйв в каждом кадре. Инвесторы стали отвечать в течение часа.', emojiReview: 'Драйв в каждом кадре 🌱 инвесторы пишут за час ⚡', beforeScore: 5.9, afterScore: 7.1, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },

  // Dating ---
  { id: 'ss-dating-yacht', category: 'dating', styleKey: 'yacht', nickname: '@stas_sea', shortReview: 'На яхте — мэтчи плывут сами ⛵', fullReview: 'На яхте — мэтчи плывут сами. Девушки в первом сообщении пишут «куда плывём?».', emojiReview: 'Мэтчи плывут сами ⛵ «куда плывём?» в первом сообщении 😉', beforeScore: 5.9, afterScore: 7.2, deltaRange: [0.4, 0.6], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-dating-cafe', category: 'dating', styleKey: 'coffee_date', nickname: '@kostya_caf', shortReview: 'В кафе — фото, к которому хочется писать 🥐', fullReview: 'В кафе — фото, к которому хочется писать. Атмосфера сразу располагает.', emojiReview: 'К которому хочется писать 🥐 атмосфера сразу 💛', beforeScore: 5.5, afterScore: 6.7, deltaRange: [0.4, 0.6], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-dating-paris', category: 'dating', styleKey: 'paris_eiffel', nickname: '@yana_dream', shortReview: 'Эйфелева — будто реально оттуда 🗼', fullReview: 'Эйфелева — будто реально оттуда. Спрашивают, как было в Париже.', emojiReview: 'Будто реально из Парижа 🗼 спрашивают, как было ✨', beforeScore: 5.8, afterScore: 7.0, deltaRange: [0.3, 0.5], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-dating-gym', category: 'dating', styleKey: 'gym_fitness', nickname: '@alex_fit', shortReview: 'Спортзал — без позёрства, по делу 💪', fullReview: 'Спортзал — без позёрства, по делу. Девушки оценили.', emojiReview: 'Без позёрства, по делу 💪 девушки оценили 🤝', beforeScore: 5.6, afterScore: 6.7, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-dating-restaurant', category: 'dating', styleKey: 'restaurant', nickname: '@den_evening', shortReview: 'Ресторан — фото уровня date-night 🍷', fullReview: 'Ресторан — фото уровня date-night. Профиль читается как «зови на ужин».', emojiReview: 'Уровень date-night 🍷 «зови на ужин» 🌙', beforeScore: 5.8, afterScore: 6.9, deltaRange: [0.3, 0.5], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-dating-yoga', category: 'dating', styleKey: 'yoga_outdoor', nickname: '@rita_calm', shortReview: 'Йога на природе — притянула «своих» 🧘', fullReview: 'Йога на природе — притянула «своих». Пишут осознанно и интересно.', emojiReview: 'Притянула «своих» 🧘 пишут осознанно 🌿', beforeScore: 5.7, afterScore: 6.8, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-dating-art', category: 'dating', styleKey: 'art_gallery', nickname: '@lev_curator', shortReview: 'Галерея — фильтр на «культурных собеседников» 🎨', fullReview: 'Галерея — фильтр на «культурных собеседников». Качество переписок другое.', emojiReview: 'Культурный фильтр 🎨 качество переписок другое 📚', beforeScore: 5.6, afterScore: 6.8, deltaRange: [0.3, 0.5], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-dating-airplane', category: 'dating', styleKey: 'airplane_window', nickname: '@nina_fly', shortReview: 'У окна самолёта — образ путешественницы ✈️', fullReview: 'У окна самолёта — образ путешественницы. Цепляет с первой ноты.', emojiReview: 'Образ путешественницы ✈️ цепляет с первой ноты 💫', beforeScore: 5.7, afterScore: 6.9, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-dating-rain', category: 'dating', styleKey: 'rainy_day', nickname: '@max_rain', shortReview: 'Дождь добавил кадру глубины 🌧', fullReview: 'Дождь добавил кадру глубины — настроение стало читаться без слов.', emojiReview: 'Глубина 🌧 настроение читается без слов 💭', beforeScore: 5.5, afterScore: 6.6, deltaRange: [0.3, 0.5], tier: 'Обычный', usage: 'style-showcase' },

  // Documents ---
  { id: 'ss-doc-3x4', category: 'documents', styleKey: 'photo_3x4', nickname: '@sasha_doc', shortReview: 'Идеальное 3×4 за 30 секунд — приняли с первого раза 📋', fullReview: 'Сделал 3×4 за 30 секунд — приняли в МФЦ с первого раза, без переделок.', emojiReview: 'Приняли с первого раза 📋 30 секунд и готово ⚡', beforeScore: 5.5, afterScore: 6.5, deltaRange: [0.02, 0.05], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-doc-passport', category: 'documents', styleKey: 'passport_rf', nickname: '@anya_passport', shortReview: 'Паспорт РФ — чёткий белый фон, всё по ГОСТу 🛂', fullReview: 'Паспорт РФ — чёткий белый фон, всё по ГОСТу. На вокзале не задавали вопросов.', emojiReview: 'Всё по ГОСТу 🛂 на вокзале без вопросов 👌', beforeScore: 5.5, afterScore: 6.5, deltaRange: [0.02, 0.05], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-doc-visa-eu', category: 'documents', styleKey: 'visa_eu', nickname: '@misha_eu', shortReview: 'Шенген — приняли в визовом центре с первого раза ✈️', fullReview: 'Шенген — лицо 70-80% кадра, без теней. Приняли в визовом центре с первого раза.', emojiReview: 'Приняли с первого раза ✈️ без теней, по требованиям 📐', beforeScore: 5.5, afterScore: 6.5, deltaRange: [0.02, 0.05], tier: 'Обычный', usage: 'style-showcase' },
  { id: 'ss-doc-visa-us', category: 'documents', styleKey: 'visa_us', nickname: '@kate_usa', shortReview: 'Виза США — квадрат 50×50, всё по DS-160 🌐', fullReview: 'Виза США — квадрат 50×50, голова в нужных пределах. Загрузила в DS-160 без правок.', emojiReview: 'DS-160 принял без правок 🌐 квадрат 50×50 ✅', beforeScore: 5.5, afterScore: 6.5, deltaRange: [0.02, 0.05], tier: 'Премиум', usage: 'style-showcase' },
  { id: 'ss-doc-4x6', category: 'documents', styleKey: 'photo_4x6', nickname: '@vlad_4x6', shortReview: '4×6 для анкеты — чисто и без лишнего стресса 📷', fullReview: '4×6 для анкеты — чисто, нейтральный фон, никакого фотоателье на районе.', emojiReview: 'Без фотоателье на районе 📷 чисто и нейтрально 🤝', beforeScore: 5.5, afterScore: 6.5, deltaRange: [0.02, 0.05], tier: 'Обычный', usage: 'style-showcase' },
];

export function getTestimonialsByCategory(category: ReviewCategory): Testimonial[] {
  return TESTIMONIALS.filter(t => t.category === category && (t.usage ?? 'carousel') === 'carousel');
}

/**
 * Returns the «under the slider» review for a specific style.
 * Strategy:
 *  1) prefer `usage: 'style-showcase'` review with matching styleKey;
 *  2) fall back to any showcase review of the same category;
 *  3) finally fall back to the carousel pool so the block never
 *     collapses on a missing styleKey (shouldn't happen, but safe).
 */
export function getStyleShowcaseReview(
  category: ReviewCategory,
  styleKey: string,
): Testimonial | undefined {
  const showcase = TESTIMONIALS.filter(
    t => t.category === category && t.usage === 'style-showcase',
  );
  const exact = showcase.find(t => t.styleKey === styleKey);
  if (exact) return exact;
  if (showcase.length > 0) {
    // Stable per-styleKey selection so re-clicking the same style
    // doesn't shuffle the review under the slider.
    let hash = 0;
    for (let i = 0; i < styleKey.length; i++) {
      hash = (hash * 31 + styleKey.charCodeAt(i)) >>> 0;
    }
    return showcase[hash % showcase.length];
  }
  return TESTIMONIALS.find(t => t.category === category);
}
