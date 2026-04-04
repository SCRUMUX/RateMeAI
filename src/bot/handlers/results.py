from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile
from redis.asyncio import Redis

from src.bot.keyboards import action_keyboard, loop_keyboard, upgrade_keyboard
from src.config import settings
from src.utils.redis_keys import gen_image_cache_key

logger = logging.getLogger(__name__)

_MAX_PHOTO_BYTES = 9 * 1024 * 1024
_MAX_CAPTION_LEN = 1024
_STORAGE_BASE = Path(settings.storage_local_path).resolve()


def _extract_storage_key(url_or_path: str) -> str | None:
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
    full_text: str | None = None,
) -> bool:
    """Try 3 strategies: Telegram URL -> httpx download -> local filesystem."""
    sent = False

    if url_or_path.startswith(("http://", "https://")):
        try:
            await bot.send_photo(
                chat_id,
                url_or_path,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=None if full_text else reply_markup,
            )
            sent = True
        except Exception:
            logger.warning("send_photo by URL failed; trying httpx download", exc_info=True)

        if not sent:
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
                        reply_markup=None if full_text else reply_markup,
                    )
                    sent = True
                else:
                    logger.warning("downloaded image too large: %s bytes", len(data))
            except Exception:
                logger.warning("httpx download failed; trying local filesystem", exc_info=True)

    if not sent:
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
                        reply_markup=None if full_text else reply_markup,
                    )
                    sent = True
                except Exception:
                    logger.exception("send_photo from local file failed: %s", local_path)

    if not sent:
        logger.error("All photo delivery methods failed for: %s", url_or_path)
        return False

    if full_text:
        try:
            await bot.send_message(chat_id, full_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            logger.exception("Failed to send follow-up text after photo")

    return True


def _bot_username() -> str:
    return settings.telegram_bot_username.lstrip("@")


def _split_caption(text: str) -> tuple[str, str | None]:
    if len(text) <= _MAX_CAPTION_LEN:
        return text, None
    truncated = text[: _MAX_CAPTION_LEN - 1] + "…"
    return truncated, text


async def _fetch_gen_image_from_redis(redis: Redis | None, task_id: str | None) -> bytes | None:
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

    needs_upgrade = result.get("upgrade_prompt", False)

    if mode == "rating":
        await _send_rating(bot, chat_id, result, user_id, uname)
    elif mode == "dating":
        await _send_dating(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade)
    elif mode == "cv":
        await _send_cv(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade)
    elif mode == "emoji":
        await _send_emoji(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade)
    else:
        kb = action_keyboard(uname, str(user_id))
        await bot.send_message(chat_id, f"Результат:\n```\n{result}\n```", parse_mode="Markdown", reply_markup=kb)


async def _send_rating(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str):
    perception = result.get("perception", {})
    score = result.get("score", "?")
    trust = perception.get("trust", "?")
    attractiveness = perception.get("attractiveness", "?")
    emotion = perception.get("emotional_expression", "")

    insights = result.get("insights", [])
    recommendations = result.get("recommendations", [])

    text_parts = [
        f"⭐ *Рейтинг: {score}/10*\n",
        f"Доверие: {trust} | Привлекательность: {attractiveness}",
        f"Эмоция: {emotion}\n",
    ]

    if insights:
        text_parts.append(f"💡 {insights[0]}")
    if len(insights) > 1:
        text_parts.append(f"💡 {insights[1]}")

    if recommendations:
        text_parts.append(f"\n🎯 {recommendations[0]}")

    text = "\n".join(text_parts)
    kb = action_keyboard(uname, str(user_id))

    share_info = result.get("share", {})
    card_path = share_info.get("card_url")

    if card_path:
        caption, full_text = _split_caption(text)
        if await _send_photo_safe(
            bot, chat_id, card_path,
            caption=caption, reply_markup=kb, full_text=full_text,
        ):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_dating(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, gen_image_bytes: bytes | None = None, needs_upgrade: bool = False):
    score = result.get("dating_score", "?")
    impression = result.get("first_impression", "")
    strengths = result.get("strengths", [])

    enhancement = result.get("enhancement", {})
    style_name = enhancement.get("style", "")

    text_parts = [f"💕 *Дейтинг: {score}/10*\n"]

    if style_name:
        style_labels = {"warm_outdoor": "На прогулке", "studio_elegant": "Студия", "cafe": "Кафе"}
        text_parts.append(f"Стиль: {style_labels.get(style_name, style_name)}")

    if impression:
        text_parts.append(f"Впечатление: {impression[:120]}")

    if strengths:
        text_parts.append(f"\n💪 {strengths[0]}")
    if len(strengths) > 1:
        text_parts.append(f"💪 {strengths[1]}")

    if needs_upgrade:
        text_parts.append("\n🔒 Генерация фото недоступна — закончились кредиты.")
    text = "\n".join(text_parts)
    kb = upgrade_keyboard() if needs_upgrade else loop_keyboard(uname, str(user_id), "dating")
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="dating_improved.jpg"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=None if full_text else kb,
            )
            if full_text:
                await bot.send_message(chat_id, full_text, parse_mode="Markdown", reply_markup=kb)
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (dating)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=caption, reply_markup=kb, full_text=full_text):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_cv(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, gen_image_bytes: bytes | None = None, needs_upgrade: bool = False):
    profession = result.get("profession", "?")
    trust = result.get("trust", "?")
    competence = result.get("competence", "?")
    hireability = result.get("hireability", "?")
    analysis = result.get("analysis", "")

    enhancement = result.get("enhancement", {})
    style_name = enhancement.get("style", "")

    text_parts = [f"💼 *Профессиональный анализ*\n"]

    if style_name:
        style_labels = {"corporate": "Корпоративный", "creative": "Креативный", "neutral": "Нейтральный"}
        text_parts.append(f"Стиль: {style_labels.get(style_name, style_name)}")

    text_parts.extend([
        f"Профессия: {profession}",
        f"Доверие: {trust} | Компетентность: {competence} | Найм: {hireability}\n",
    ])

    if analysis:
        text_parts.append(f"📝 {analysis[:200]}")

    if needs_upgrade:
        text_parts.append("\n🔒 Генерация фото недоступна — закончились кредиты.")
    text = "\n".join(text_parts)
    kb = upgrade_keyboard() if needs_upgrade else loop_keyboard(uname, str(user_id), "cv")
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="cv_improved.jpg"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=None if full_text else kb,
            )
            if full_text:
                await bot.send_message(chat_id, full_text, parse_mode="Markdown", reply_markup=kb)
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (cv)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=caption, reply_markup=kb, full_text=full_text):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_emoji(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, gen_image_bytes: bytes | None = None, needs_upgrade: bool = False):
    base_desc = result.get("base_description", "")
    stickers = result.get("stickers", [])

    text_parts = ["😀 *Эмодзи-пак*\n"]
    if base_desc:
        text_parts.append(f"{base_desc[:150]}\n")

    if stickers:
        emoji_map = {
            "happy": "😊", "sad": "😢", "angry": "😠", "surprised": "😲",
            "love": "😍", "cool": "😎", "thinking": "🤔", "laughing": "😂",
            "sleepy": "😴", "wink": "😉", "scared": "😱", "party": "🎉",
        }
        for s in stickers[:6]:
            emotion = s.get("emotion", "")
            icon = emoji_map.get(emotion, "•")
            text_parts.append(f"{icon} {emotion}: {s.get('description', '')[:60]}")

    if needs_upgrade:
        text_parts.append("\n🔒 Генерация фото недоступна — закончились кредиты.")
    text = "\n".join(text_parts)
    kb = upgrade_keyboard() if needs_upgrade else action_keyboard(uname, str(user_id))
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="emoji_sticker.jpg"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=None if full_text else kb,
            )
            if full_text:
                await bot.send_message(chat_id, full_text, parse_mode="Markdown", reply_markup=kb)
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (emoji)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=caption, reply_markup=kb, full_text=full_text):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
