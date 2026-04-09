import type { CategoryId } from './styles';

export interface Testimonial {
  id: string;
  styleKey: string;
  category: CategoryId;
  nickname: string;
  shortReview: string;
  fullReview: string;
  beforeScore: number;
  afterScore: number;
  deltaRange: [number, number];
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
    beforeScore: 5.82,
    afterScore: 6.71,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'social-2',
    styleKey: 'golden_hour',
    category: 'social',
    nickname: '@alex_photo',
    shortReview: 'Golden hour эффект — именно то, чего не хватало моим фото',
    fullReview: 'Всегда завидовал блогерам с идеальным светом на фотках. Стиль Golden hour дал мне именно тот тёплый свет, который раньше получался только на закате. Engagement rate вырос на 40%, а я просто загрузил обычное фото из дома.',
    beforeScore: 5.44,
    afterScore: 6.58,
    deltaRange: [0.35, 0.55],
  },
  {
    id: 'social-3',
    styleKey: 'influencer_urban',
    category: 'social',
    nickname: '@kate_lifestyle',
    shortReview: 'Мой Instagram наконец выглядит как у топ-блогеров',
    fullReview: 'Я веду lifestyle-блог и мне всегда не хватало «того самого» визуала. Urban блогер стиль превратил мои обычные уличные фото в контент уровня журнала. Три последних поста залетели в рекомендации. Это реально работает.',
    beforeScore: 6.01,
    afterScore: 7.12,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'social-4',
    styleKey: 'neon_night',
    category: 'social',
    nickname: '@dmitry_beats',
    shortReview: 'Неоновый стиль идеально зашёл для моей музыкальной страницы',
    fullReview: 'Я продвигаю свою музыку в соцсетях и неоновый стиль оказался идеальным для моего бренда. Каждый пост получает на 50% больше сохранений. Фото выглядят как кадры из клипа, а я потратил 30 секунд.',
    beforeScore: 5.67,
    afterScore: 6.89,
    deltaRange: [0.35, 0.55],
  },
  {
    id: 'social-5',
    styleKey: 'candid_street',
    category: 'social',
    nickname: '@anya_moments',
    shortReview: 'Случайные кадры стали выглядеть как спланированная съёмка',
    fullReview: 'Раньше мои «случайные» фото выглядели именно как случайные — без стиля и атмосферы. Теперь каждый кадр с улицы превращается в эстетичный контент. Друзья думают, что я наняла фотографа. Очень довольна результатом!',
    beforeScore: 5.33,
    afterScore: 6.42,
    deltaRange: [0.25, 0.45],
  },

  // --- CV ---
  {
    id: 'cv-1',
    styleKey: 'corporate',
    category: 'cv',
    nickname: '@sergey_pm',
    shortReview: 'HR написала, что моё фото на LinkedIn произвело сильное впечатление',
    fullReview: 'Обновил фото на LinkedIn с помощью корпоративного стиля. Через неделю получил 3 приглашения на собеседования. HR одной компании отдельно отметила, что моё фото выглядит очень профессионально. Инвестиция в 1 кредит окупилась многократно.',
    beforeScore: 5.71,
    afterScore: 6.93,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'cv-2',
    styleKey: 'speaker_stage',
    category: 'cv',
    nickname: '@elena_ceo',
    shortReview: 'Стиль «Спикер» добавил авторитетности моему профилю',
    fullReview: 'Как основатель стартапа мне важно выглядеть уверенно. Стиль «Спикер» создал ощущение, что я выступаю на крупной конференции. Инвесторы стали воспринимать меня серьёзнее — и это видно по конверсии моих питчей.',
    beforeScore: 5.88,
    afterScore: 7.14,
    deltaRange: [0.35, 0.55],
  },
  {
    id: 'cv-3',
    styleKey: 'tech_developer',
    category: 'cv',
    nickname: '@max_dev',
    shortReview: 'Наконец-то нормальное фото для GitHub и резюме',
    fullReview: 'Как разработчику мне всегда было лень делать нормальное фото для профиля. IT-стиль сделал из моего домашнего селфи профессиональный портрет. Поставил на GitHub, LinkedIn и резюме — отклики выросли вдвое.',
    beforeScore: 5.22,
    afterScore: 6.45,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'cv-4',
    styleKey: 'startup_casual',
    category: 'cv',
    nickname: '@liza_product',
    shortReview: 'Стартап-стиль — ровно между формальным и дружелюбным',
    fullReview: 'Работаю продакт-менеджером и классический костюм — не мой стиль. «Стартап» попал в точку: выгляжу профессионально, но без лишней формальности. Идеально для IT-компаний. Коллеги спрашивают, где я делала фото.',
    beforeScore: 5.95,
    afterScore: 6.88,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'cv-5',
    styleKey: 'mentor',
    category: 'cv',
    nickname: '@igor_coach',
    shortReview: 'Клиенты стали записываться чаще — фото внушает доверие',
    fullReview: 'Я бизнес-коуч, и мне важно выглядеть открытым, но компетентным. Стиль «Ментор» идеально передал этот баланс. После смены фото на сайте количество записей на консультации выросло на 25%. Рекомендую всем, кто работает с людьми.',
    beforeScore: 5.64,
    afterScore: 6.97,
    deltaRange: [0.35, 0.55],
  },

  // --- Dating ---
  {
    id: 'dating-1',
    styleKey: 'paris_eiffel',
    category: 'dating',
    nickname: '@natasha_travel',
    shortReview: 'Мэтчей стало в 5 раз больше — фото у башни работает магически',
    fullReview: 'Загрузила своё обычное фото и выбрала Эйфелеву башню. Результат — как будто я реально там побывала с профессиональным фотографом. За первую неделю мэтчей стало в 5 раз больше. Парни пишут первыми и спрашивают про Париж.',
    beforeScore: 5.91,
    afterScore: 7.05,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'dating-2',
    styleKey: 'coffee_date',
    category: 'dating',
    nickname: '@andrey_msk',
    shortReview: 'Фото в кафе сделало профиль намного теплее и привлекательнее',
    fullReview: 'Мой друг посоветовал сервис после того как сам нашёл девушку в Tinder. Стиль «В кафе» превратил скучный портрет в уютное фото, от которого хочется познакомиться. Количество лайков удвоилось за пару дней.',
    beforeScore: 5.55,
    afterScore: 6.68,
    deltaRange: [0.25, 0.45],
  },
  {
    id: 'dating-3',
    styleKey: 'dog_lover',
    category: 'dating',
    nickname: '@olga_sunny',
    shortReview: 'Фото с собакой — лучшее решение для dating-профиля!',
    fullReview: 'У меня нет собаки, но фото с ней получилось настолько естественным! Девочки в приложении знакомств реагируют невероятно тепло. Это фото стало моим главным в профиле. Искренность и тепло — именно то, что нужно для первого впечатления.',
    beforeScore: 5.78,
    afterScore: 7.01,
    deltaRange: [0.35, 0.55],
  },
  {
    id: 'dating-4',
    styleKey: 'beach_sunset',
    category: 'dating',
    nickname: '@vika_sea',
    shortReview: 'Закатное фото добавило романтики — переписки стали длиннее',
    fullReview: 'Выбрала стиль «На закате» и не пожалела. Золотой свет сделал фото невероятно мягким и притягательным. Заметила, что люди стали писать более длинные и вдумчивые первые сообщения. Атмосфера фото задаёт тон общению.',
    beforeScore: 6.10,
    afterScore: 7.22,
    deltaRange: [0.35, 0.55],
  },
  {
    id: 'dating-5',
    styleKey: 'rooftop_city',
    category: 'dating',
    nickname: '@mark_night',
    shortReview: 'Вид с крыши + уверенный взгляд = идеальное фото для анкеты',
    fullReview: 'Стиль «На крыше» добавил моему профилю ощущение успешности и уверенности. Фото выглядит дорого и стильно, при этом естественно. Получил больше 50 мэтчей за первую неделю. Лучшая инвестиция в dating-профиль.',
    beforeScore: 5.42,
    afterScore: 6.79,
    deltaRange: [0.35, 0.55],
  },
];

export function getTestimonialsByCategory(category: CategoryId): Testimonial[] {
  return TESTIMONIALS.filter(t => t.category === category);
}
