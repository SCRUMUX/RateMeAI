from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def scenario_keyboard() -> InlineKeyboardMarkup:
    """Primary 3-button scenario selection (no Rating in main flow)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f495 Знакомства", callback_data="pick_style:dating")],
        [InlineKeyboardButton(text="\U0001f4bc Карьера", callback_data="pick_style:cv")],
        [InlineKeyboardButton(text="\U0001f4f8 Соцсети", callback_data="pick_style:social")],
    ])


# Legacy alias — some handlers still reference this
mode_selection_keyboard = scenario_keyboard

# ---------------------------------------------------------------------------
# Full style catalogs — ordered by display priority (page 1 = first 6)
# ---------------------------------------------------------------------------

_PAGE_SIZE = 6

STYLE_CATALOG: dict[str, list[tuple[str, str]]] = {
    "dating": [
        # --- Landmarks (wow-effect) ---
        ("paris_eiffel", "\U0001f5fc Эйфелева башня"),
        ("dubai_burj_khalifa", "\U0001f3d9 Бурдж-Халифа"),
        ("nyc_brooklyn_bridge", "\U0001f309 Бруклинский мост"),
        ("rome_colosseum", "\U0001f3db Колизей"),
        ("venice_san_marco", "\U0001f6f6 Венеция"),
        ("barcelona_sagrada", "\u2600\ufe0f Барселона"),
        # ---
        ("london_eye", "\U0001f3a1 Лондон"),
        ("tokyo_tower", "\U0001f5fc Токио"),
        ("singapore_marina_bay", "\U0001f307 Сингапур"),
        ("sf_golden_gate", "\U0001f309 Золотые Ворота"),
        ("athens_acropolis", "\U0001f3db Афины"),
        ("sydney_opera", "\U0001f3b6 Сидней"),
        # ---
        ("nyc_times_square", "\U0001f4a1 Таймс-сквер"),
        ("nyc_central_park", "\U0001f333 Центральный парк"),
        ("london_big_ben", "\U0001f554 Биг-Бен"),
        # --- Travel ---
        ("airplane_window", "\u2708\ufe0f У окна самолёта"),
        ("hotel_breakfast", "\U0001f373 Завтрак в отеле"),
        ("sea_balcony", "\U0001f30a Балкон с видом на море"),
        # ---
        ("old_town_walk", "\U0001f3d8 Старый город"),
        ("train_journey", "\U0001f682 В поезде"),
        ("street_market", "\U0001f6d2 Уличный рынок"),
        ("hotel_checkin", "\U0001f3e8 Лобби отеля"),
        ("travel_luxury", "\U0001f48e Travel luxury"),
        ("car_exit", "\U0001f697 Выход из авто"),
        # --- Lifestyle ---
        ("near_car", "\U0001f697 У машины"),
        ("yacht", "\u26f5 На яхте"),
        ("coffee_date", "\u2615 В кафе"),
        ("beach_sunset", "\U0001f305 На закате"),
        ("dog_lover", "\U0001f415 С собакой"),
        ("rooftop_city", "\U0001f303 На крыше"),
        # --- Sport ---
        ("gym_fitness", "\U0001f4aa Спортзал"),
        ("running", "\U0001f3c3 Пробежка"),
        ("swimming_pool", "\U0001f3ca Бассейн"),
        ("hiking", "\u26f0 Поход"),
        ("yoga_outdoor", "\U0001f9d8 Йога"),
        ("cycling", "\U0001f6b4 Велопрогулка"),
        ("tennis", "\U0001f3be Теннис"),
        # --- Atmosphere ---
        ("restaurant", "\U0001f377 Ресторан"),
        ("bar_lounge", "\U0001f378 Бар"),
        ("cooking", "\U0001f468\u200d\U0001f373 На кухне"),
        ("rainy_day", "\U0001f327 В дождь"),
        ("night_coffee", "\u2615 Ночной кофе"),
        ("evening_home", "\U0001f3e0 Вечер дома"),
        # --- Classic ---
        ("motorcycle", "\U0001f3cd Мотоцикл"),
        ("in_car", "\U0001f698 В машине"),
        ("art_gallery", "\U0001f3a8 Галерея"),
        ("street_urban", "\U0001f3d9 Улица"),
        ("concert", "\U0001f3b8 Музыкант"),
        ("travel", "\u2708\ufe0f Аэропорт"),
        ("warm_outdoor", "\U0001f324 На прогулке"),
        ("studio_elegant", "\u2728 Студия"),
        ("cafe", "\u2615 Кафе / бар"),
    ],
    "cv": [
        # --- Classic ---
        ("corporate", "\U0001f3e2 Корпоративный"),
        ("boardroom", "\U0001f4cb Переговорная"),
        ("formal_portrait", "\U0001f4f7 Формальный портрет"),
        ("glass_wall_pose", "\U0001f3e2 У стеклянной стены"),
        ("startup_casual", "\U0001f680 Стартап"),
        ("coworking", "\U0001f465 Коворкинг"),
        # --- Career ---
        ("video_call", "\U0001f4f9 Созвон"),
        ("analytics_review", "\U0001f4ca Аналитика"),
        ("notebook_ideas", "\U0001f4dd Запись идей"),
        ("tablet_stylus", "\U0001f4f1 Планшет"),
        ("coffee_break_work", "\u2615 Перерыв с кофе"),
        ("late_hustle", "\U0001f319 Вечерняя работа"),
        # --- Moments ---
        ("before_meeting", "\U0001f4bc Перед встречей"),
        ("between_meetings", "\U0001f4f1 Между встречами"),
        ("decision_moment", "\U0001f3d9 Момент решения"),
        ("business_lounge", "\u2708\ufe0f Бизнес-лаунж"),
        ("speaker_stage", "\U0001f3a4 Спикер"),
        ("standing_desk", "\U0001f5a5 Домашний офис"),
        # --- Archetypes ---
        ("digital_nomad", "\U0001f310 Digital nomad"),
        ("quiet_expert", "\U0001f4da Тихий эксперт"),
        ("intellectual", "\U0001f393 Интеллектуал"),
        ("entrepreneur_on_move", "\U0001f680 Предприниматель"),
        ("man_with_mission", "\U0001f3af Человек с миссией"),
        # --- Industries ---
        ("tech_developer", "\U0001f4bb IT разработчик"),
        ("creative_director", "\U0001f3a8 Креативный директор"),
        ("medical", "\U0001f3e5 Медицина"),
        ("legal_finance", "\u2696\ufe0f Юрист / Финансы"),
        ("architect", "\U0001f4d0 Архитектор"),
        ("podcast", "\U0001f3a7 Подкастер"),
        ("mentor", "\U0001f91d Ментор"),
        ("outdoor_business", "\u2600\ufe0f Бизнес на террасе"),
        ("creative", "\U0001f3a8 Креативный"),
        ("neutral", "\U0001f4f7 Нейтральный фон"),
    ],
    "social": [
        # --- Aesthetic ---
        ("mirror_aesthetic", "\U0001faa9 У зеркала"),
        ("elevator_clean", "\U0001f6d7 В лифте"),
        ("candid_street", "\U0001f4f8 Случайный кадр"),
        ("book_and_coffee", "\U0001f4d6 Книга и кофе"),
        ("shopfront", "\U0001f6cd У витрины"),
        ("focused_mood", "\U0001f440 Фокус"),
        # --- Influencer ---
        ("influencer_urban", "\U0001f303 Urban блогер"),
        ("influencer_luxury", "\U0001f48e Luxury"),
        ("influencer_minimal", "\u26aa Минимализм"),
        ("golden_hour", "\U0001f31f Golden hour"),
        ("neon_night", "\U0001f4a0 Неон"),
        ("tinder_top", "\U0001f525 Для Tinder"),
        # --- Hobbies ---
        ("reading_home", "\U0001f4da Чтение дома"),
        ("reading_cafe", "\u2615 Чтение в кафе"),
        ("sketching", "\u270f\ufe0f Скетчинг"),
        ("photographer", "\U0001f4f7 Фотограф"),
        ("meditation", "\U0001f9d8 Медитация"),
        ("online_learning", "\U0001f4bb Обучение"),
        # --- Sport ---
        ("yoga_social", "\U0001f9d8 Йога"),
        ("cycling_social", "\U0001f6b4 Велопрогулка"),
        ("fitness_lifestyle", "\U0001f4aa Фитнес"),
        # --- Cinematic ---
        ("panoramic_window", "\U0001f303 Панорамное окно"),
        ("in_motion", "\U0001f3c3 В движении"),
        ("creative_insight", "\U0001f4a1 Креативный инсайт"),
        ("architecture_shadow", "\U0001f3db Тень архитектуры"),
        ("achievement_moment", "\U0001f3c6 Момент победы"),
        ("light_irony", "\U0001f60f Лёгкая ирония"),
        # --- Evening ---
        ("skyscraper_view", "\U0001f307 Вид с небоскрёба"),
        ("after_work", "\U0001f306 После работы"),
        ("evening_planning", "\U0001f4dd Вечернее планирование"),
        ("dark_moody", "\U0001f311 Dark moody"),
        ("vintage_film", "\U0001f4f7 Винтаж"),
        ("pastel_soft", "\U0001f338 Пастель"),
        # --- Platforms ---
        ("instagram_aesthetic", "\U0001f4f8 Instagram"),
        ("youtube_creator", "\U0001f3ac YouTube"),
        ("linkedin_premium", "\U0001f4bc LinkedIn"),
        ("podcast_host", "\U0001f3a7 Подкаст"),
        ("creative_portrait", "\U0001f3a8 Арт-портрет"),
        # --- Classic ---
        ("morning_routine", "\u2600\ufe0f Утро"),
        ("food_blogger", "\U0001f37d Фуд-блогер"),
        ("travel_blogger", "\u2708\ufe0f Тревел-блогер"),
        ("influencer", "\U0001f31f Influencer"),
        ("luxury", "\U0001f48e Luxury classic"),
        ("casual", "\u2600\ufe0f Casual"),
        ("artistic", "\U0001f3a8 Artistic"),
    ],
}


def style_keyboard(mode: str, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated style selection: 6 per page, 2 per row, with navigation."""
    catalog = STYLE_CATALOG.get(mode, [])
    start = page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    items = catalog[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(text=items[i][1], callback_data=f"style:{mode}:{items[i][0]}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(text=items[i + 1][1], callback_data=f"style:{mode}:{items[i + 1][0]}"))
        rows.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="\u2b05\ufe0f Назад", callback_data=f"styles_page:{mode}:{page - 1}"))
    if end < len(catalog):
        nav_row.append(InlineKeyboardButton(text="Ещё стили \u27a1\ufe0f", callback_data=f"styles_page:{mode}:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def dating_style_keyboard() -> InlineKeyboardMarkup:
    return style_keyboard("dating")


def cv_style_keyboard() -> InlineKeyboardMarkup:
    return style_keyboard("cv")


def social_style_keyboard() -> InlineKeyboardMarkup:
    return style_keyboard("social")


def post_result_keyboard(
    mode: str,
    user_id: str,
    bot_username: str,
    next_options: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    """Post-result: 2 next-level buttons + share + new photo."""
    deep_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    rows = []

    if next_options and len(next_options) >= 2:
        rows.append([
            InlineKeyboardButton(text=next_options[0]["label"], callback_data=next_options[0]["callback_data"]),
            InlineKeyboardButton(text=next_options[1]["label"], callback_data=next_options[1]["callback_data"]),
        ])
    elif mode == "dating":
        rows.append([
            InlineKeyboardButton(text="\U0001f525 Уверенный", callback_data="enhance:dating:charismatic"),
            InlineKeyboardButton(text="\U0001f3a8 Другой стиль", callback_data="restyle:dating"),
        ])
    elif mode == "cv":
        rows.append([
            InlineKeyboardButton(text="\U0001f4bc Строже", callback_data="enhance:cv:corporate"),
            InlineKeyboardButton(text="\U0001f3a8 Другой стиль", callback_data="restyle:cv"),
        ])
    elif mode == "social":
        rows.append([
            InlineKeyboardButton(text="\U0001f31f Ярче", callback_data="enhance:social:influencer"),
            InlineKeyboardButton(text="\U0001f3a8 Другой стиль", callback_data="restyle:social"),
        ])
    elif mode == "rating":
        rows.append([
            InlineKeyboardButton(text="\U0001f495 Знакомства", callback_data="pick_style:dating"),
            InlineKeyboardButton(text="\U0001f4bc Карьера", callback_data="pick_style:cv"),
        ])

    rows.extend([
        [
            InlineKeyboardButton(text="\U0001f4e4 Друзьям", switch_inline_query=deep_link),
            InlineKeyboardButton(text="\U0001f4f8 Новое фото", callback_data="new_photo"),
        ],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Legacy aliases for backward compatibility
def action_keyboard(bot_username: str, user_id: str) -> InlineKeyboardMarkup:
    return post_result_keyboard("dating", user_id, bot_username)


def loop_keyboard(bot_username: str, user_id: str, current_mode: str) -> InlineKeyboardMarkup:
    return post_result_keyboard(current_mode, user_id, bot_username)


def error_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f504 Попробовать снова", callback_data="retry")],
        [InlineKeyboardButton(text="\U0001f4f8 Новое фото", callback_data="new_photo")],
    ])


def upgrade_keyboard() -> InlineKeyboardMarkup:
    from src.services.payments import get_credit_packs
    rows = []
    for pack in get_credit_packs():
        rows.append([InlineKeyboardButton(
            text=f"\U0001f6d2 {pack.label}",
            callback_data=f"buy:{pack.quantity}",
        )])
    rows.append([InlineKeyboardButton(text="\U0001f4b0 Мой баланс", callback_data="balance")])
    rows.append([InlineKeyboardButton(text="\U0001f4f8 Новое фото", callback_data="new_photo")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4f8 Загрузить фото", callback_data="new_photo")],
    ])
