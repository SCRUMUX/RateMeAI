from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY
from src.bot.keyboards import scenario_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.photo)
async def handle_photo(message: Message, redis: Redis):
    """Store the photo file_id in Redis and show scenario selection."""
    photo = message.photo[-1]
    user_id = message.from_user.id

    await redis.set(PHOTO_KEY.format(user_id), photo.file_id, ex=86400)

    rating_flag = await redis.get(f"ratemeai:rating_mode:{user_id}")
    if rating_flag:
        await redis.delete(f"ratemeai:rating_mode:{user_id}")
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2b50 Получить рейтинг", callback_data="mode:rating")],
        ])
        await message.answer("\u2b50 Анализирую фото для рейтинга:", reply_markup=kb)
        return

    await message.answer(
        "Выбери направление, и я подберу лучший образ:",
        reply_markup=scenario_keyboard(),
    )


@router.message(F.document)
async def handle_document(message: Message, redis: Redis):
    content_type = message.document.mime_type or ""
    if content_type.startswith("image/"):
        user_id = message.from_user.id
        await redis.set(PHOTO_KEY.format(user_id), message.document.file_id, ex=86400)

        rating_flag = await redis.get(f"ratemeai:rating_mode:{user_id}")
        if rating_flag:
            await redis.delete(f"ratemeai:rating_mode:{user_id}")
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\u2b50 Получить рейтинг", callback_data="mode:rating")],
            ])
            await message.answer("\u2b50 Анализирую фото для рейтинга:", reply_markup=kb)
            return

        await message.answer(
            "Выбери направление, и я подберу лучший образ:",
            reply_markup=scenario_keyboard(),
        )
    else:
        from src.bot.keyboards import back_keyboard
        await message.answer(
            "Пожалуйста, отправь фотографию (изображение).",
            reply_markup=back_keyboard(),
        )
