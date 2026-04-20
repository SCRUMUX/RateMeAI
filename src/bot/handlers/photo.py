from __future__ import annotations

import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY
from src.bot.handlers.consent import ensure_consents
from src.bot.keyboards import scenario_keyboard, back_keyboard
from src.bot.utils.photo import download_photo_bytes
from src.services.input_quality import analyze_input_quality, InputQualityReport
from src.utils.image import validate_and_normalize

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
        # Score keys include style suffix: ratemeai:score:{user}:{mode}:{style}
        pattern = f"ratemeai:score:{user_id}:{mode}:*"
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break


async def _run_preflight(message: Message, file_id: str) -> InputQualityReport | None:
    """Download Telegram file and run input quality gate.

    Returns the report on success (can be empty of issues). Returns None if
    download failed — caller should treat this as a soft error and proceed.
    Sends a rejection message directly to the user if the gate blocks the photo
    and returns None in that case too.
    """
    try:
        raw = await download_photo_bytes(message.bot, file_id)
        raw, _ = await asyncio.to_thread(validate_and_normalize, raw)
    except Exception:
        logger.warning("Pre-flight: failed to download/normalize photo", exc_info=True)
        return None

    report = await asyncio.to_thread(analyze_input_quality, raw)
    if not report.can_generate:
        lines = ["\u26a0\ufe0f *Это фото не подойдёт для генерации.*", ""]
        for issue in report.blocking:
            lines.append(f"• {issue.message} {issue.suggestion}".rstrip())
        lines.append("")
        lines.append("Пришли другое фото или набери /photo\\_help для подробностей.")
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard())
        return None
    return report


def _format_soft_warnings(report: InputQualityReport) -> str:
    """Compact warning block appended to the scenario-selection message."""
    if not report.soft_warnings:
        return ""
    lines = ["", "\u26a0\ufe0f *Обрати внимание на качество фото:*"]
    for w in report.soft_warnings:
        lines.append(f"• {w.message}")
    lines.append("Продолжим — но результат может отличаться от оригинала.")
    return "\n".join(lines)


@router.message(F.photo)
async def handle_photo(message: Message, redis: Redis, api_base_url: str):
    """Pre-flight check, store file_id in Redis and show scenario selection."""
    try:
        photo = message.photo[-1]
        user_id = message.from_user.id
        logger.info("Photo received from user %s, file_id=%s", user_id, photo.file_id[:20])

        if not await ensure_consents(message, redis, api_base_url):
            return

        report = await _run_preflight(message, photo.file_id)
        if report is None:
            return

        await redis.set(PHOTO_KEY.format(user_id), photo.file_id, ex=86400)
        await _reset_depth(redis, user_id)

        mode_redirect = await _check_mode_flags(redis, user_id)
        if mode_redirect:
            await message.answer(mode_redirect["text"], reply_markup=mode_redirect["kb"])
            return

        text = "Выбери направление, и я подберу лучший образ:" + _format_soft_warnings(report)
        await message.answer(
            text,
            reply_markup=scenario_keyboard(),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("handle_photo failed for user %s", message.from_user.id if message.from_user else "?")
        await message.answer("Произошла ошибка при обработке фото. Попробуй /start", parse_mode=None)


@router.message(F.document)
async def handle_document(message: Message, redis: Redis, api_base_url: str):
    try:
        content_type = message.document.mime_type or ""
        if content_type.startswith("image/"):
            user_id = message.from_user.id
            if not await ensure_consents(message, redis, api_base_url):
                return
            report = await _run_preflight(message, message.document.file_id)
            if report is None:
                return

            await redis.set(PHOTO_KEY.format(user_id), message.document.file_id, ex=86400)
            await _reset_depth(redis, user_id)

            mode_redirect = await _check_mode_flags(redis, user_id)
            if mode_redirect:
                await message.answer(mode_redirect["text"], reply_markup=mode_redirect["kb"])
                return

            text = "Выбери направление, и я подберу лучший образ:" + _format_soft_warnings(report)
            await message.answer(
                text,
                reply_markup=scenario_keyboard(),
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                "Пожалуйста, отправь фотографию (изображение).",
                reply_markup=back_keyboard(),
            )
    except Exception:
        logger.exception("handle_document failed for user %s", message.from_user.id if message.from_user else "?")
        await message.answer("Произошла ошибка при обработке файла. Попробуй /start", parse_mode=None)
