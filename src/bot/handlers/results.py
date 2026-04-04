from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile
from redis.asyncio import Redis

from src.bot.keyboards import result_keyboard
from src.config import settings
from src.utils.redis_keys import gen_image_cache_key

logger = logging.getLogger(__name__)

_MAX_PHOTO_BYTES = 9 * 1024 * 1024
_STORAGE_BASE = Path(settings.storage_local_path).resolve()


def _extract_storage_key(url_or_path: str) -> str | None:
    """Extract storage key from URL like http://host/storage/gen/uid/tid.jpg or a relative path."""
    marker = "/storage/"
    idx = url_or_path.find(marker)
    if idx >= 0:
        return url_or_path[idx + len(marker):]
    if not url_or_path.startswith(("http://", "https://")):
        return url_or_path
    return None


async def _send_photo_safe(
    bot: Bot,
    chat_id: int,
    url_or_path: str,
    *,
    caption: str,
    reply_markup,
) -> bool:
    """Try 3 strategies: Telegram URL → httpx download → local filesystem."""
    if url_or_path.startswith(("http://", "https://")):
        try:
            await bot.send_photo(
                chat_id,
                url_or_path,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return True
        except Exception:
            logger.warning("send_photo by URL failed; trying httpx download", exc_info=True)

        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                resp = await client.get(url_or_path)
                resp.raise_for_status()
                data = resp.content
            if len(data) <= _MAX_PHOTO_BYTES:
                await bot.send_photo(
                    chat_id,
                    BufferedInputFile(data, filename="photo.jpg"),
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                return True
            logger.warning("downloaded image too large: %s bytes", len(data))
        except Exception:
            logger.warning("httpx download failed; trying local filesystem", exc_info=True)

    key = _extract_storage_key(url_or_path)
    if key:
        local_path = _STORAGE_BASE / key
        if local_path.exists() and local_path.is_file():
            try:
                await bot.send_photo(
                    chat_id,
                    FSInputFile(str(local_path)),
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                return True
            except Exception:
                logger.exception("send_photo from local file failed: %s", local_path)

    logger.error("All photo delivery methods failed for: %s", url_or_path)
    return False


def _bot_username() -> str:
    return settings.telegram_bot_username.lstrip("@")


async def _fetch_gen_image_from_redis(redis: Redis | None, task_id: str | None) -> bytes | None:
    """Try to load generated image bytes from Redis staging."""
    if not redis or not task_id:
        return None
    try:
        b64 = await redis.get(gen_image_cache_key(task_id))
        if b64:
            await redis.delete(gen_image_cache_key(task_id))
            data = base64.b64decode(b64)
            logger.info("Loaded generated image from Redis for task %s (%d bytes)", task_id, len(data))
            return data
    except Exception:
        logger.exception("Failed to load generated image from Redis for task %s", task_id)
    return None


async def deliver_result(bot: Bot, chat_id: int, status_msg_id: int, data: dict, user_id: int, redis: Redis | None = None):
    """Format and send analysis result to user."""
    result = data.get("result", {})
    mode = data.get("mode", "rating")
    task_id = str(data.get("task_id", ""))

    gen_image_bytes: bytes | None = None
    if result.get("generated_image_url"):
        gen_image_bytes = await _fetch_gen_image_from_redis(redis, task_id)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
    except Exception:
        pass

    uname = _bot_username()

    if mode == "rating":
        await _send_rating(bot, chat_id, result, user_id, uname)
    elif mode == "dating":
        await _send_dating(bot, chat_id, result, user_id, uname, gen_image_bytes)
    elif mode == "cv":
        await _send_cv(bot, chat_id, result, user_id, uname, gen_image_bytes)
    elif mode == "emoji":
        await _send_emoji(bot, chat_id, result, user_id, uname, gen_image_bytes)
    else:
        await bot.send_message(chat_id, f"Результат:\n```\n{result}\n```", parse_mode="Markdown")


async def _send_rating(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str):
    perception = result.get("perception", {})
    score = result.get("score", "?")
    trust = perception.get("trust", "?")
    attractiveness = perception.get("attractiveness", "?")
    emotion = perception.get("emotional_expression", "")

    insights = result.get("insights", [])
    recommendations = result.get("recommendations", [])

    text_parts = [
        f"⭐ **Твой рейтинг: {score}/10**\n",
        f"🤝 Доверие: {trust}/10",
        f"✨ Привлекательность: {attractiveness}/10",
        f"🎭 Эмоция: {emotion}\n",
    ]

    if insights:
        text_parts.append("💡 **Инсайты:**")
        for i, ins in enumerate(insights[:3], 1):
            text_parts.append(f"  {i}. {ins}")
        text_parts.append("")

    if recommendations:
        text_parts.append("🎯 **Рекомендации:**")
        for i, rec in enumerate(recommendations[:3], 1):
            text_parts.append(f"  {i}. {rec}")

    text = "\n".join(text_parts)

    share_info = result.get("share", {})
    card_path = share_info.get("card_url")

    if card_path:
        if await _send_photo_safe(
            bot,
            chat_id,
            card_path,
            caption=text,
            reply_markup=result_keyboard(uname, str(user_id)),
        ):
            return

    await bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown",
        reply_markup=result_keyboard(uname, str(user_id)),
    )


async def _send_dating(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, gen_image_bytes: bytes | None = None):
    score = result.get("dating_score", "?")
    impression = result.get("first_impression", "")
    strengths = result.get("strengths", [])
    weaknesses = result.get("weaknesses", [])
    variants = result.get("variants", [])

    text_parts = [
        f"💕 **Дейтинг-анализ: {score}/10**\n",
        f"Первое впечатление: {impression}\n",
    ]

    if strengths:
        text_parts.append("💪 **Сильные стороны:**")
        for s in strengths[:3]:
            text_parts.append(f"  • {s}")
        text_parts.append("")

    if weaknesses:
        text_parts.append("📌 **Можно улучшить:**")
        for w in weaknesses[:3]:
            text_parts.append(f"  • {w}")
        text_parts.append("")

    if variants:
        text_parts.append("🎭 **Варианты улучшения:**")
        for v in variants[:3]:
            vtype = v.get("type", "")
            explanation = v.get("explanation", "")
            text_parts.append(f"\n  **{vtype.capitalize()}:** {explanation}")

    text = "\n".join(text_parts)
    kb = result_keyboard(uname, str(user_id))

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="dating_improved.jpg"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (dating)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=text, reply_markup=kb):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_cv(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, gen_image_bytes: bytes | None = None):
    profession = result.get("profession", "?")
    trust = result.get("trust", "?")
    competence = result.get("competence", "?")
    hireability = result.get("hireability", "?")
    analysis = result.get("analysis", "")

    text = (
        f"💼 **Профессиональный анализ**\n"
        f"Профессия: {profession}\n\n"
        f"🤝 Доверие: {trust}/10\n"
        f"🧠 Компетентность: {competence}/10\n"
        f"📋 Шанс на собеседование: {hireability}/10\n\n"
        f"📝 {analysis}"
    )
    kb = result_keyboard(uname, str(user_id))

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="cv_improved.jpg"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (cv)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=text, reply_markup=kb):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_emoji(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, gen_image_bytes: bytes | None = None):
    base_desc = result.get("base_description", "")
    stickers = result.get("stickers", [])

    text_parts = [f"😀 **Эмодзи-пак**\n", f"Базовое описание: {base_desc}\n"]

    if stickers:
        text_parts.append("Стикеры:")
        for s in stickers[:12]:
            emoji_map = {
                "happy": "😊", "sad": "😢", "angry": "😠", "surprised": "😲",
                "love": "😍", "cool": "😎", "thinking": "🤔", "laughing": "😂",
                "sleepy": "😴", "wink": "😉", "scared": "😱", "party": "🎉",
            }
            emotion = s.get("emotion", "")
            icon = emoji_map.get(emotion, "•")
            text_parts.append(f"  {icon} {emotion}: {s.get('description', '')[:80]}")

    text = "\n".join(text_parts)
    kb = result_keyboard(uname, str(user_id))

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="emoji_sticker.jpg"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (emoji)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=text, reply_markup=kb):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
