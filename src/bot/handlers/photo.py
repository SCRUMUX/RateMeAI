from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY
from src.bot.keyboards import scenario_keyboard

router = Router()
logger = logging.getLogger(__name__)

_DEPTH_MODES = ("dating", "cv", "social")


async def _check_mode_flags(redis: Redis, user_id: int) -> dict | None:
    """Check if a special mode flag (rating/emoji) is set and return redirect info."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    rating_flag = await redis.get(f"ratemeai:rating_mode:{user_id}")
    if rating_flag:
        await redis.delete(f"ratemeai:rating_mode:{user_id}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2b50 Получить рейтинг", callback_data="mode:rating")],
        ])
        return {"text": "\u2b50 Анализирую фото для рейтинга:", "kb": kb}

    emoji_flag = await redis.get(f"ratemeai:emoji_mode:{user_id}")
    if emoji_flag:
        await redis.delete(f"ratemeai:emoji_mode:{user_id}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f600 Создать эмодзи", callback_data="mode:emoji")],
        ])
        return {"text": "\U0001f600 Создаю эмодзи-стикер:", "kb": kb}

    return None


async def _reset_depth(redis: Redis, user_id: int) -> None:
    """Clear depth tracking and accumulated scores for all modes when a new photo is uploaded."""
    for mode in _DEPTH_MODES:
        await redis.delete(f"ratemeai:depth:{user_id}:{mode}")
        await redis.delete(f"ratemeai:score:{user_id}:{mode}")


@router.message(F.photo)
async def handle_photo(message: Message, redis: Redis):
    """Store the photo file_id in Redis and show scenario selection."""
    photo = message.photo[-1]
    user_id = message.from_user.id

    await redis.set(PHOTO_KEY.format(user_id), photo.file_id, ex=86400)
    await _reset_depth(redis, user_id)

    mode_redirect = await _check_mode_flags(redis, user_id)
    if mode_redirect:
        await message.answer(mode_redirect["text"], reply_markup=mode_redirect["kb"])
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
        await _reset_depth(redis, user_id)

        mode_redirect = await _check_mode_flags(redis, user_id)
        if mode_redirect:
            await message.answer(mode_redirect["text"], reply_markup=mode_redirect["kb"])
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
