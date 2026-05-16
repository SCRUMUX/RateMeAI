"""Catch-all handlers for unrecognized messages and callbacks."""

from __future__ import annotations

import time

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from redis.asyncio import Redis

from src.bot.keyboards import back_keyboard
from src.bot.handlers.results import LAST_GEN_AT_KEY
from src.config import settings

router = Router()

# How recently a result must have been shown for the fallback to switch
# into "post-result CTA" mode.  Shorter than the TTL of the marker so we
# never flip into the friendly mode after the marker has aged out.
_POST_RESULT_WINDOW_SECONDS = 300


def _post_result_keyboard() -> InlineKeyboardMarkup:
    """CTA shown when the user types something right after a result."""
    bot_username = settings.telegram_bot_username.lstrip("@")
    deep_link = f"https://t.me/{bot_username}"
    share_text = f"Попробуй AI-стилиста: {deep_link}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f4e4 Поделиться с другом",
                    switch_inline_query=share_text,
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4f8 Новое фото", callback_data="new_photo"
                ),
                InlineKeyboardButton(
                    text="\U0001f4b3 Пополнить", callback_data="topup"
                ),
            ],
        ]
    )


async def _within_post_result_window(redis: Redis, user_id: int) -> bool:
    try:
        raw = await redis.get(LAST_GEN_AT_KEY.format(user_id))
    except Exception:
        return False
    if not raw:
        return False
    try:
        ts = int(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        return False
    return (time.time() - ts) <= _POST_RESULT_WINDOW_SECONDS


@router.message()
async def catch_all_message(message: Message, redis: Redis):
    user_id = message.from_user.id if message.from_user else 0
    if user_id and await _within_post_result_window(redis, user_id):
        await message.answer(
            "\U0001f60a Понравился результат? Поделись с другом или попробуй другой стиль.",
            reply_markup=_post_result_keyboard(),
        )
        return
    await message.answer(
        "\U0001f4f8 Отправь мне фото, и я подберу лучший образ!",
        reply_markup=back_keyboard(),
    )


@router.callback_query()
async def catch_all_callback(callback: CallbackQuery):
    await callback.answer("Неизвестная команда. Отправь фото!")
