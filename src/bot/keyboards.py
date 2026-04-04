from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.models.enums import AnalysisMode


def mode_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Рейтинг", callback_data=f"mode:{AnalysisMode.RATING.value}"),
            InlineKeyboardButton(text="💕 Дейтинг", callback_data="pick_style:dating"),
        ],
        [
            InlineKeyboardButton(text="💼 Резюме/CV", callback_data="pick_style:cv"),
            InlineKeyboardButton(text="😀 Эмодзи-пак", callback_data=f"mode:{AnalysisMode.EMOJI.value}"),
        ],
    ])


def dating_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 На прогулке", callback_data="style:dating:warm_outdoor")],
        [InlineKeyboardButton(text="✨ Студия / элегант", callback_data="style:dating:studio_elegant")],
        [InlineKeyboardButton(text="☕ Кафе / бар", callback_data="style:dating:cafe")],
    ])


def cv_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Корпоративный", callback_data="style:cv:corporate")],
        [InlineKeyboardButton(text="🎨 Креативный", callback_data="style:cv:creative")],
        [InlineKeyboardButton(text="📷 Нейтральный фон", callback_data="style:cv:neutral")],
    ])


def action_keyboard(bot_username: str, user_id: str) -> InlineKeyboardMarkup:
    """Post-result keyboard: mode switching + share + new photo."""
    deep_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💕 Дейтинг-фото", callback_data="action:dating"),
            InlineKeyboardButton(text="💼 CV-фото", callback_data="action:cv"),
        ],
        [
            InlineKeyboardButton(text="😀 Эмодзи", callback_data="action:emoji"),
            InlineKeyboardButton(text="⭐ Рейтинг", callback_data="action:rating"),
        ],
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=deep_link)],
        [InlineKeyboardButton(text="📸 Новое фото", callback_data="new_photo")],
    ])


def loop_keyboard(bot_username: str, user_id: str, current_mode: str) -> InlineKeyboardMarkup:
    """Post-generation keyboard with refinement options."""
    deep_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    rows = []
    if current_mode == "dating":
        rows.append([
            InlineKeyboardButton(text="🔥 Привлекательнее", callback_data="loop:dating:charismatic"),
            InlineKeyboardButton(text="🎨 Другой стиль", callback_data="restyle:dating"),
        ])
    elif current_mode == "cv":
        rows.append([
            InlineKeyboardButton(text="💼 Профессиональнее", callback_data="loop:cv:corporate"),
            InlineKeyboardButton(text="🎨 Другой стиль", callback_data="restyle:cv"),
        ])
    rows.extend([
        [
            InlineKeyboardButton(text="💕 Дейтинг", callback_data="action:dating"),
            InlineKeyboardButton(text="💼 CV", callback_data="action:cv"),
            InlineKeyboardButton(text="😀 Эмодзи", callback_data="action:emoji"),
        ],
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=deep_link)],
        [InlineKeyboardButton(text="📸 Новое фото", callback_data="new_photo")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def error_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="retry")],
        [InlineKeyboardButton(text="📸 Новое фото", callback_data="new_photo")],
    ])


def upgrade_keyboard() -> InlineKeyboardMarkup:
    from src.services.payments import get_credit_packs
    rows = []
    for pack in get_credit_packs():
        rows.append([InlineKeyboardButton(
            text=f"🛒 {pack.label}",
            callback_data=f"buy:{pack.quantity}",
        )])
    rows.append([InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance")])
    rows.append([InlineKeyboardButton(text="📸 Новое фото", callback_data="new_photo")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Загрузить фото", callback_data="new_photo")],
    ])
