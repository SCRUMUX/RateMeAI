from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY
from src.bot.keyboards import mode_selection_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.photo)
async def handle_photo(message: Message, redis: Redis):
    """Store the photo file_id in Redis and show mode selection."""
    photo = message.photo[-1]
    user_id = message.from_user.id

    await redis.set(PHOTO_KEY.format(user_id), photo.file_id, ex=3600)

    await message.answer(
        "📸 Отличное фото! Выбери, что хочешь узнать:",
        reply_markup=mode_selection_keyboard(),
    )


@router.message(F.document)
async def handle_document(message: Message, redis: Redis):
    content_type = message.document.mime_type or ""
    if content_type.startswith("image/"):
        await redis.set(PHOTO_KEY.format(message.from_user.id), message.document.file_id, ex=3600)
        await message.answer(
            "📸 Фото получено! Выбери режим:",
            reply_markup=mode_selection_keyboard(),
        )
    else:
        await message.answer("Пожалуйста, отправь фотографию (изображение).")
