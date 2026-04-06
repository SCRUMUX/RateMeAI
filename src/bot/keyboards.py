from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.models.enums import AnalysisMode


def scenario_keyboard() -> InlineKeyboardMarkup:
    """Primary 3-button scenario selection (no Rating in main flow)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f495 Знакомства", callback_data="pick_style:dating")],
        [InlineKeyboardButton(text="\U0001f4bc Карьера", callback_data="pick_style:cv")],
        [InlineKeyboardButton(text="\U0001f4f8 Соцсети", callback_data="pick_style:social")],
    ])


# Legacy alias — some handlers still reference this
mode_selection_keyboard = scenario_keyboard


def dating_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f305 На прогулке", callback_data="style:dating:warm_outdoor")],
        [InlineKeyboardButton(text="\u2728 Студия / элегант", callback_data="style:dating:studio_elegant")],
        [InlineKeyboardButton(text="\u2615 Кафе / бар", callback_data="style:dating:cafe")],
    ])


def cv_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f3e2 Корпоративный", callback_data="style:cv:corporate")],
        [InlineKeyboardButton(text="\U0001f3a8 Креативный", callback_data="style:cv:creative")],
        [InlineKeyboardButton(text="\U0001f4f7 Нейтральный фон", callback_data="style:cv:neutral")],
    ])


def social_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f31f Influencer", callback_data="style:social:influencer")],
        [InlineKeyboardButton(text="\U0001f48e Luxury", callback_data="style:social:luxury")],
        [InlineKeyboardButton(text="\u2600\ufe0f Casual", callback_data="style:social:casual")],
        [InlineKeyboardButton(text="\U0001f3a8 Artistic", callback_data="style:social:artistic")],
    ])


def enhancement_choice_keyboard(
    option_a_label: str,
    option_a_data: str,
    option_b_label: str,
    option_b_data: str,
) -> InlineKeyboardMarkup:
    """Binary choice — always exactly 2 buttons side by side."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=option_a_label, callback_data=option_a_data),
            InlineKeyboardButton(text=option_b_label, callback_data=option_b_data),
        ],
    ])


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
    else:
        if mode == "dating":
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
