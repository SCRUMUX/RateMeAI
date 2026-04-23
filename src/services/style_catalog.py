"""Shared style catalog — single source of truth for bot keyboards + web API.

Each entry: (style_key, display_label, hook_text, meta)
where meta = {"param": warmth|presence|appeal, "delta_range": (min, max)}
"""

from __future__ import annotations

STYLE_CATALOG: dict[str, list[tuple[str, str, str, dict]]] = {
    "dating": [
        # --- Landmarks ---
        (
            "paris_eiffel",
            "\U0001f5fc Эйфелева башня",
            "Романтичный кадр у башни подчеркнёт лёгкость и вкус",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "dubai_burj_khalifa",
            "\U0001f3d9 Бурдж-Халифа",
            "Амбициозный фон добавит ощущение успеха и масштаба",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "nyc_brooklyn_bridge",
            "\U0001f309 Бруклинский мост",
            "Городская романтика усилит харизму и уверенность",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "rome_colosseum",
            "\U0001f3db Колизей",
            "Величие античности подчеркнёт глубину характера",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "venice_san_marco",
            "\U0001f6f6 Венеция",
            "Атмосфера каналов создаст ощущение утончённости",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "barcelona_sagrada",
            "\u2600\ufe0f Барселона",
            "Тёплый свет Барселоны усилит открытость и обаяние",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "london_eye",
            "\U0001f3a1 Лондон",
            "Стильный британский фон добавит элегантности",
            {"param": "appeal", "delta_range": (0.15, 0.30)},
        ),
        (
            "tokyo_tower",
            "\U0001f5fc Токио",
            "Японская эстетика подчеркнёт современность и вкус",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "singapore_marina_bay",
            "\U0001f307 Сингапур",
            "Футуристичный фон усилит впечатление успешности",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "sf_golden_gate",
            "\U0001f309 Золотые Ворота",
            "Калифорнийский свет добавит лёгкости и свободы",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "athens_acropolis",
            "\U0001f3db Афины",
            "Классическая красота подчеркнёт силу и характер",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "sydney_opera",
            "\U0001f3b6 Сидней",
            "Яркий фон создаст впечатление открытого человека",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "nyc_times_square",
            "\U0001f4a1 Таймс-сквер",
            "Энергия мегаполиса подчеркнёт уверенность и драйв",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "nyc_central_park",
            "\U0001f333 Центральный парк",
            "Природа в городе создаст ощущение гармонии",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "london_big_ben",
            "\U0001f554 Биг-Бен",
            "Классический фон усилит надёжность образа",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        # --- Travel ---
        (
            "airplane_window",
            "\u2708\ufe0f У окна самолёта",
            "Путешественник — это всегда интригующе и привлекательно",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "hotel_breakfast",
            "\U0001f373 Завтрак в отеле",
            "Уютный кадр подчеркнёт вкус к жизни",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "sea_balcony",
            "\U0001f30a Балкон с видом на море",
            "Морской фон усилит спокойствие и притягательность",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "old_town_walk",
            "\U0001f3d8 Старый город",
            "Прогулка по улочкам добавит романтичности",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "train_journey",
            "\U0001f682 В поезде",
            "Динамика поездки подчеркнёт авантюризм и лёгкость",
            {"param": "appeal", "delta_range": (0.15, 0.30)},
        ),
        (
            "street_market",
            "\U0001f6d2 Уличный рынок",
            "Живая атмосфера рынка покажет открытость миру",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "hotel_checkin",
            "\U0001f3e8 Лобби отеля",
            "Стильный интерьер добавит статуса и ухоженности",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "travel_luxury",
            "\U0001f48e Travel luxury",
            "Премиальная обстановка усилит впечатление успеха",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "car_exit",
            "\U0001f697 Выход из авто",
            "Уверенный жест подчеркнёт стиль и статус",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        # --- Lifestyle ---
        (
            "near_car",
            "\U0001f697 У машины",
            "Уверенная поза у авто добавит мужественности",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "yacht",
            "\u26f5 На яхте",
            "Морской кадр создаст ощущение свободы и достатка",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "coffee_date",
            "\u2615 В кафе",
            "Тёплая атмосфера кафе усилит располагающий образ",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "beach_sunset",
            "\U0001f305 На закате",
            "Золотой свет заката подчеркнёт мягкость и тепло",
            {"param": "warmth", "delta_range": (0.35, 0.55)},
        ),
        (
            "dog_lover",
            "\U0001f415 С собакой",
            "Фото с питомцем добавит искренности и доверия",
            {"param": "warmth", "delta_range": (0.35, 0.55)},
        ),
        (
            "rooftop_city",
            "\U0001f303 На крыше",
            "Вид сверху создаст ощущение уверенности и масштаба",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        # --- Sport ---
        (
            "gym_fitness",
            "\U0001f4aa Спортзал",
            "Спортивный кадр покажет дисциплину и энергию",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "running",
            "\U0001f3c3 Пробежка",
            "Динамичная поза подчеркнёт активность и здоровье",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "swimming_pool",
            "\U0001f3ca Бассейн",
            "Свежий образ у воды усилит привлекательность",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "hiking",
            "\u26f0 Поход",
            "Природный фон покажет характер и выносливость",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "yoga_outdoor",
            "\U0001f9d8 Йога",
            "Гармоничная поза усилит ощущение внутренней силы",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "cycling",
            "\U0001f6b4 Велопрогулка",
            "Активный кадр добавит лёгкости и динамики",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "tennis",
            "\U0001f3be Теннис",
            "Элегантный спорт подчеркнёт стиль и энергичность",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        # --- Atmosphere ---
        (
            "restaurant",
            "\U0001f377 Ресторан",
            "Ресторанный свет подчеркнёт утончённость и вкус",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "bar_lounge",
            "\U0001f378 Бар",
            "Приглушённый свет бара добавит загадочности",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "cooking",
            "\U0001f468\u200d\U0001f373 На кухне",
            "Кулинарный кадр покажет заботу и домашнее тепло",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "rainy_day",
            "\U0001f327 В дождь",
            "Атмосфера дождя добавит глубины и чувственности",
            {"param": "appeal", "delta_range": (0.15, 0.30)},
        ),
        (
            "night_coffee",
            "\u2615 Ночной кофе",
            "Вечернее настроение создаст интимную атмосферу",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "evening_home",
            "\U0001f3e0 Вечер дома",
            "Домашний уют покажет искренность и тепло",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        # --- Classic ---
        (
            "motorcycle",
            "\U0001f3cd Мотоцикл",
            "Дерзкий образ подчеркнёт смелость и свободу",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "in_car",
            "\U0001f698 В машине",
            "Кадр за рулём добавит уверенности и стиля",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "art_gallery",
            "\U0001f3a8 Галерея",
            "Культурный фон подчеркнёт интеллект и вкус",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "street_urban",
            "\U0001f3d9 Улица",
            "Городская энергия добавит современности образу",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "concert",
            "\U0001f3b8 Музыкант",
            "Творческий кадр покажет страсть и индивидуальность",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "travel",
            "\u2708\ufe0f Аэропорт",
            "Образ путешественника подчеркнёт независимость",
            {"param": "appeal", "delta_range": (0.15, 0.30)},
        ),
        (
            "warm_outdoor",
            "\U0001f324 На прогулке",
            "Естественный свет подчеркнёт натуральность и тепло",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "studio_elegant",
            "\u2728 Студия",
            "Студийный свет создаст безупречный портрет",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "cafe",
            "\u2615 Кафе / бар",
            "Расслабленная обстановка покажет лёгкость в общении",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "tinder_pack_rooftop_golden",
            "\U0001f306 Руфтоп золотой час",
            "Тёплый городской закат для максимального свайпа вправо",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "tinder_pack_minimal_studio",
            "\u2728 Минимал студия",
            "Чистый портрет без отвлекающих деталей",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "tinder_pack_cafe_window",
            "\u2615 Кафе у окна",
            "Уютный свет и естественная улыбка",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
    ],
    "cv": [
        (
            "corporate",
            "\U0001f3e2 Корпоративный",
            "Деловой фон усилит впечатление надёжности",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "boardroom",
            "\U0001f4cb Переговорная",
            "Переговорная покажет лидерские качества",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "formal_portrait",
            "\U0001f4f7 Формальный портрет",
            "Классический портрет повысит доверие с первого взгляда",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "glass_wall_pose",
            "\U0001f3e2 У стеклянной стены",
            "Современный офис подчеркнёт прогрессивность",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "startup_casual",
            "\U0001f680 Стартап",
            "Непринуждённый стиль покажет гибкость и инновационность",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "coworking",
            "\U0001f465 Коворкинг",
            "Открытое пространство усилит командный дух",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "video_call",
            "\U0001f4f9 Созвон",
            "Идеальный кадр для профессиональных созвонов",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "analytics_review",
            "\U0001f4ca Аналитика",
            "Аналитический фокус подчеркнёт экспертность",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "notebook_ideas",
            "\U0001f4dd Запись идей",
            "Рабочий момент покажет вдумчивость и глубину",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "tablet_stylus",
            "\U0001f4f1 Планшет",
            "Технологичный образ подчеркнёт современность",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "coffee_break_work",
            "\u2615 Перерыв с кофе",
            "Рабочий перерыв покажет человечность и баланс",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "late_hustle",
            "\U0001f319 Вечерняя работа",
            "Вечерний кадр подчеркнёт целеустремлённость",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "before_meeting",
            "\U0001f4bc Перед встречей",
            "Сосредоточенность перед встречей усилит серьёзность",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "between_meetings",
            "\U0001f4f1 Между встречами",
            "Динамичный ритм покажет востребованность",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "decision_moment",
            "\U0001f3d9 Момент решения",
            "Уверенный взгляд подчеркнёт решительность",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "business_lounge",
            "\u2708\ufe0f Бизнес-лаунж",
            "Премиальный фон усилит восприятие статуса",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "speaker_stage",
            "\U0001f3a4 Спикер",
            "Сцена подчеркнёт авторитет и экспертность",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "standing_desk",
            "\U0001f5a5 Домашний офис",
            "Современный формат покажет адаптивность",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "digital_nomad",
            "\U0001f310 Digital nomad",
            "Свободный стиль работы подчеркнёт независимость",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "quiet_expert",
            "\U0001f4da Тихий эксперт",
            "Спокойная уверенность усилит доверие к экспертизе",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "intellectual",
            "\U0001f393 Интеллектуал",
            "Интеллектуальный образ подчеркнёт глубину знаний",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "entrepreneur_on_move",
            "\U0001f680 Предприниматель",
            "Динамика действия покажет предпринимательский дух",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "man_with_mission",
            "\U0001f3af Человек с миссией",
            "Целеустремлённость подчеркнёт лидерский потенциал",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "tech_developer",
            "\U0001f4bb IT разработчик",
            "Техническая среда усилит восприятие компетентности",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "creative_director",
            "\U0001f3a8 Креативный директор",
            "Творческий фон покажет нестандартное мышление",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "medical",
            "\U0001f3e5 Медицина",
            "Профессиональный фон усилит доверие пациентов",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "legal_finance",
            "\u2696\ufe0f Юрист / Финансы",
            "Строгий стиль подчеркнёт надёжность и точность",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "architect",
            "\U0001f4d0 Архитектор",
            "Пространственный фон покажет визуальное мышление",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "podcast",
            "\U0001f3a7 Подкастер",
            "Медиа-формат подчеркнёт коммуникабельность",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "mentor",
            "\U0001f91d Ментор",
            "Открытая поза покажет готовность помогать другим",
            {"param": "warmth", "delta_range": (0.35, 0.55)},
        ),
        (
            "outdoor_business",
            "\u2600\ufe0f Бизнес на террасе",
            "Свежий воздух подчеркнёт баланс и стиль жизни",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "creative",
            "\U0001f3a8 Креативный",
            "Творческий подход покажет оригинальность мышления",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "neutral",
            "\U0001f4f7 Нейтральный фон",
            "Чистый фон сфокусирует внимание на личности",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "doc_passport_neutral",
            "\U0001faa6 Паспорт / ID",
            "Ровный свет и нейтральный фон для документов",
            {"param": "presence", "delta_range": (0.10, 0.20)},
        ),
        (
            "doc_visa_compliant",
            "\u2708\ufe0f Виза",
            "Деловой нейтральный образ для консульских фото",
            {"param": "presence", "delta_range": (0.12, 0.22)},
        ),
        (
            "doc_resume_headshot",
            "\U0001f4bc Резюме / LinkedIn",
            "Уверенный деловой портрет на светлом фоне",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "photo_3x4",
            "\U0001f4cb 3\u00d74 стандарт",
            "30\u00d740 мм, лицо 70\u201380%, нейтральное выражение",
            {"param": "trust", "delta_range": (0.02, 0.05)},
        ),
        (
            "passport_rf",
            "\U0001f6c2 Паспорт РФ",
            "35\u00d745 мм, строго фронтально, белый фон",
            {"param": "trust", "delta_range": (0.02, 0.05)},
        ),
        (
            "visa_eu",
            "\u2708\ufe0f Виза / Шенген",
            "35\u00d745 мм, лицо 70\u201380%, без теней",
            {"param": "trust", "delta_range": (0.02, 0.05)},
        ),
        (
            "visa_us",
            "\U0001f310 Виза США",
            "50\u00d750 мм, квадрат, голова 25\u201335 мм",
            {"param": "trust", "delta_range": (0.02, 0.05)},
        ),
        (
            "photo_4x6",
            "\U0001f4f7 4\u00d76 универсал",
            "40\u00d760 мм, менее строгие требования",
            {"param": "trust", "delta_range": (0.02, 0.05)},
        ),
    ],
    "social": [
        (
            "mirror_aesthetic",
            "\U0001faa9 У зеркала",
            "Зеркальный кадр добавит стиля и уверенности",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "elevator_clean",
            "\U0001f6d7 В лифте",
            "Чистый минималистичный кадр привлечёт внимание",
            {"param": "appeal", "delta_range": (0.15, 0.30)},
        ),
        (
            "candid_street",
            "\U0001f4f8 Случайный кадр",
            "Естественность подчеркнёт искренность и живость",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "book_and_coffee",
            "\U0001f4d6 Книга и кофе",
            "Уютная атмосфера создаст вовлекающий контент",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "shopfront",
            "\U0001f6cd У витрины",
            "Городской фон усилит стильность образа",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "focused_mood",
            "\U0001f440 Фокус",
            "Сфокусированный взгляд притянет внимание зрителей",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "influencer_urban",
            "\U0001f303 Urban блогер",
            "Городская эстетика усилит трендовый образ",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "influencer_luxury",
            "\U0001f48e Luxury",
            "Премиум-обстановка создаст вау-эффект в ленте",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "influencer_minimal",
            "\u26aa Минимализм",
            "Чистый стиль подчеркнёт вкус и современность",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "golden_hour",
            "\U0001f31f Golden hour",
            "Золотой свет сделает кадр тёплым и запоминающимся",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "neon_night",
            "\U0001f4a0 Неон",
            "Неоновый свет создаст яркий цепляющий контент",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "tinder_top",
            "\U0001f525 Для Tinder",
            "Максимальная привлекательность для анкеты",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "reading_home",
            "\U0001f4da Чтение дома",
            "Домашний кадр покажет глубину и интеллект",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "reading_cafe",
            "\u2615 Чтение в кафе",
            "Атмосфера кафе добавит стиля к увлечению",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "sketching",
            "\u270f\ufe0f Скетчинг",
            "Творческий момент покажет талант и индивидуальность",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "photographer",
            "\U0001f4f7 Фотограф",
            "Камера в руках подчеркнёт творческий взгляд",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "meditation",
            "\U0001f9d8 Медитация",
            "Гармоничный кадр усилит ощущение внутренней силы",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "online_learning",
            "\U0001f4bb Обучение",
            "Образовательный контент подчеркнёт развитие",
            {"param": "warmth", "delta_range": (0.15, 0.30)},
        ),
        (
            "yoga_social",
            "\U0001f9d8 Йога",
            "Спокойная сила привлечёт осознанную аудиторию",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "cycling_social",
            "\U0001f6b4 Велопрогулка",
            "Активный образ жизни вдохновит подписчиков",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "fitness_lifestyle",
            "\U0001f4aa Фитнес",
            "Спортивный кадр покажет дисциплину и энергию",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "panoramic_window",
            "\U0001f303 Панорамное окно",
            "Вид из окна создаст кинематографичный контент",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "in_motion",
            "\U0001f3c3 В движении",
            "Динамика кадра передаст энергию и драйв",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "creative_insight",
            "\U0001f4a1 Креативный инсайт",
            "Момент вдохновения подчеркнёт креативность",
            {"param": "appeal", "delta_range": (0.15, 0.30)},
        ),
        (
            "architecture_shadow",
            "\U0001f3db Тень архитектуры",
            "Архитектурный свет добавит глубины и арта",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "achievement_moment",
            "\U0001f3c6 Момент победы",
            "Триумфальный кадр вызовет восхищение аудитории",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "light_irony",
            "\U0001f60f Лёгкая ирония",
            "Ироничный образ покажет чувство юмора и стиль",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "skyscraper_view",
            "\U0001f307 Вид с небоскрёба",
            "Панорамный фон создаст ощущение достижений",
            {"param": "presence", "delta_range": (0.35, 0.55)},
        ),
        (
            "after_work",
            "\U0001f306 После работы",
            "Вечерний свет добавит атмосферности контенту",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "evening_planning",
            "\U0001f4dd Вечернее планирование",
            "Рабочий вечер подчеркнёт серьёзность намерений",
            {"param": "presence", "delta_range": (0.15, 0.30)},
        ),
        (
            "dark_moody",
            "\U0001f311 Dark moody",
            "Контрастный стиль создаст запоминающийся образ",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "vintage_film",
            "\U0001f4f7 Винтаж",
            "Ретро-обработка добавит уникальности и ностальгии",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "pastel_soft",
            "\U0001f338 Пастель",
            "Мягкие тона создадут нежный эстетичный контент",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "instagram_aesthetic",
            "\U0001f4f8 Instagram",
            "Идеальная эстетика для Instagram-ленты",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "youtube_creator",
            "\U0001f3ac YouTube",
            "Динамичный кадр усилит узнаваемость канала",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "linkedin_premium",
            "\U0001f4bc LinkedIn",
            "Профессиональный кадр повысит доверие коллег",
            {"param": "presence", "delta_range": (0.25, 0.45)},
        ),
        (
            "podcast_host",
            "\U0001f3a7 Подкаст",
            "Медийный образ подчеркнёт экспертность и голос",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "creative_portrait",
            "\U0001f3a8 Арт-портрет",
            "Художественный подход выделит из массы контента",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "morning_routine",
            "\u2600\ufe0f Утро",
            "Утренний свет создаст свежий и энергичный образ",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "food_blogger",
            "\U0001f37d Фуд-блогер",
            "Гастрономический кадр покажет стиль жизни",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "travel_blogger",
            "\u2708\ufe0f Тревел-блогер",
            "Путешествия вдохновят и привлекут аудиторию",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "influencer",
            "\U0001f31f Influencer",
            "Инфлюенсерский стиль усилит вовлечённость",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
        (
            "luxury",
            "\U0001f48e Luxury classic",
            "Премиальный образ создаст эффект роскоши",
            {"param": "appeal", "delta_range": (0.35, 0.55)},
        ),
        (
            "casual",
            "\u2600\ufe0f Casual",
            "Лёгкий стиль подчеркнёт естественность и вкус",
            {"param": "warmth", "delta_range": (0.25, 0.45)},
        ),
        (
            "artistic",
            "\U0001f3a8 Artistic",
            "Арт-стиль покажет креативность и уникальный взгляд",
            {"param": "appeal", "delta_range": (0.25, 0.45)},
        ),
    ],
}


def get_catalog_json(mode: str) -> list[dict]:
    """Return catalog for a mode as JSON-friendly list of dicts."""
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    items = []

    for s in styles:
        if s.get("mode") == mode and not s.get("is_scenario_only", False):
            items.append(
                {
                    "key": s["id"],
                    "label": s.get("display_label", s["id"]),
                    "hook": s.get("hook_text", ""),
                    "meta": s.get("meta", {}),
                    "category": s.get("category", "General"),
                    "unlock_after_generations": s.get("unlock_after_generations", 0),
                }
            )

    return items


def get_available_modes() -> list[str]:
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    modes = set(s.get("mode") for s in styles if s.get("mode"))
    return list(modes)


def get_style_options(style_id: str) -> dict | None:
    """Return allowed variations for a specific style."""
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    for s in styles:
        if s["id"] == style_id:
            return s.get("allowed_variations", {})
    return None
