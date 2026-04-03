from __future__ import annotations

import logging
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile

from src.bot.keyboards import result_keyboard
from src.config import settings

logger = logging.getLogger(__name__)

_MAX_PHOTO_BYTES = 9 * 1024 * 1024
_STORAGE_BASE = Path(settings.storage_local_path).resolve()


async def _send_photo_from_public_url(
    bot: Bot,
    chat_id: int,
    url: str,
    *,
    caption: str,
    reply_markup,
) -> bool:
    """Telegram loads URL from its servers; on failure, download and send as bytes."""
    try:
        await bot.send_photo(
            chat_id,
            url,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        logger.warning(
            "send_photo by URL failed (Telegram may not reach URL); retrying via download",
            exc_info=True,
        )
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
        if len(data) > _MAX_PHOTO_BYTES:
            logger.warning("downloaded image too large for Telegram: %s bytes", len(data))
            return False
        await bot.send_photo(
            chat_id,
            BufferedInputFile(data, filename="photo.jpg"),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        logger.exception("send_photo after download failed")
        return False


def _bot_username() -> str:
    return settings.telegram_bot_username.lstrip("@")


async def deliver_result(bot: Bot, chat_id: int, status_msg_id: int, data: dict, user_id: int):
    """Format and send analysis result to user."""
    result = data.get("result", {})
    mode = data.get("mode", "rating")

    try:
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
    except Exception:
        pass

    uname = _bot_username()

    if mode == "rating":
        await _send_rating(bot, chat_id, result, user_id, uname)
    elif mode == "dating":
        await _send_dating(bot, chat_id, result, user_id, uname)
    elif mode == "cv":
        await _send_cv(bot, chat_id, result, user_id, uname)
    elif mode == "emoji":
        await _send_emoji(bot, chat_id, result, user_id, uname)
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
        try:
            if card_path.startswith("http://") or card_path.startswith("https://"):
                if await _send_photo_from_public_url(
                    bot,
                    chat_id,
                    card_path,
                    caption=text,
                    reply_markup=result_keyboard(uname, str(user_id)),
                ):
                    return

            absolute_path = _STORAGE_BASE / card_path
            photo = FSInputFile(str(absolute_path))
            await bot.send_photo(
                chat_id,
                photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=result_keyboard(uname, str(user_id)),
            )
            return
        except Exception:
            logger.exception("Failed to send share card")

    await bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown",
        reply_markup=result_keyboard(uname, str(user_id)),
    )


async def _send_dating(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str):
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

    img = result.get("generated_image_url") or result.get("image_url")
    if img and (img.startswith("http://") or img.startswith("https://")):
        if await _send_photo_from_public_url(
            bot,
            chat_id,
            img,
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


async def _send_cv(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str):
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
    img = result.get("generated_image_url") or result.get("image_url")
    if img and (img.startswith("http://") or img.startswith("https://")):
        if await _send_photo_from_public_url(
            bot,
            chat_id,
            img,
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


async def _send_emoji(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str):
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

    img = result.get("generated_image_url") or result.get("image_url")
    if img and (img.startswith("http://") or img.startswith("https://")):
        if await _send_photo_from_public_url(
            bot,
            chat_id,
            img,
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
