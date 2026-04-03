from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.models.enums import AnalysisMode


def mode_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Рейтинг", callback_data=f"mode:{AnalysisMode.RATING.value}"),
            InlineKeyboardButton(text="💕 Дейтинг", callback_data=f"mode:{AnalysisMode.DATING.value}"),
        ],
        [
            InlineKeyboardButton(text="💼 Резюме/CV", callback_data=f"mode:{AnalysisMode.CV.value}"),
            InlineKeyboardButton(text="😀 Эмодзи-пак", callback_data=f"mode:{AnalysisMode.EMOJI.value}"),
        ],
    ])


def result_keyboard(bot_username: str, user_id: str) -> InlineKeyboardMarkup:
    deep_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=deep_link)],
        [InlineKeyboardButton(text="📸 Загрузить другое фото", callback_data="new_photo")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Загрузить фото", callback_data="new_photo")],
    ])
