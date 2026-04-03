from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message

from src.bot.keyboards import mode_selection_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.photo)
async def handle_photo(message: Message):
    """Store the photo file_id in FSM-like state (user data) and show mode selection."""
    photo = message.photo[-1]  # highest resolution

    # Store in bot_data keyed by user for the next step
    user_id = message.from_user.id

    # We use a simple dict on the bot object for ephemeral state
    if not hasattr(message.bot, "_user_photos"):
        message.bot._user_photos = {}
    message.bot._user_photos[user_id] = photo.file_id

    await message.answer(
        "📸 Отличное фото! Выбери, что хочешь узнать:",
        reply_markup=mode_selection_keyboard(),
    )


@router.message(F.document)
async def handle_document(message: Message):
    content_type = message.document.mime_type or ""
    if content_type.startswith("image/"):
        if not hasattr(message.bot, "_user_photos"):
            message.bot._user_photos = {}
        message.bot._user_photos[message.from_user.id] = message.document.file_id
        await message.answer(
            "📸 Фото получено! Выбери режим:",
            reply_markup=mode_selection_keyboard(),
        )
    else:
        await message.answer("Пожалуйста, отправь фотографию (изображение).")
