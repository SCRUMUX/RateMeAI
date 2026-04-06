from __future__ import annotations

import base64
import hashlib
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
    truncated = text[: _MAX_CAPTION_LEN - 1] + "\u2026"
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


async def _get_credit_balance(user_id: int) -> int | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            api_base = settings.api_base_url
            resp = await client.get(
                f"{api_base}/api/v1/payments/balance",
                headers={"X-Telegram-Id": str(user_id)},
            )
        if resp.status_code == 200:
            return resp.json().get("image_credits")
    except Exception:
        logger.debug("Could not fetch balance for user %s", user_id)
    return None


_MODE_SUGGESTIONS: dict[str, list[str]] = {
    "dating": [
        "Попробуй образ *Студия / элегант* \u2014 он часто да\u0451т +1-2 к привлекательности!",
        "Хочешь ещ\u0451 больше? Попробуй стиль *Кафе / бар* для непринужд\u0451нного образа.",
    ],
    "cv": [
        "Попробуй *Корпоративный* стиль \u2014 он максимально повышает доверие.",
        "Для творческих профессий подойд\u0451т *Креативный* образ!",
    ],
    "social": [
        "Попробуй стиль *Luxury* \u2014 он отлично работает для Instagram.",
        "Стиль *Artistic* может дать ещ\u0451 более яркий результат!",
    ],
}


def _retention_line(result: dict, mode: str, chat_id: int) -> str:
    """Return an inline retention hint string, or empty string."""
    if mode not in ("dating", "cv", "social"):
        return ""

    delta = result.get("delta", {})
    if not delta:
        return ""

    has_improvement = False
    if mode == "dating" and delta.get("dating_score"):
        has_improvement = delta["dating_score"].get("delta", 0) > 0
    elif mode == "cv":
        for key in ("trust", "competence", "hireability"):
            if delta.get(key, {}).get("delta", 0) > 0:
                has_improvement = True
                break
    elif mode == "social" and delta.get("social_score"):
        has_improvement = delta["social_score"].get("delta", 0) > 0

    if not has_improvement:
        return ""

    suggestions = _MODE_SUGGESTIONS.get(mode, [])
    if not suggestions:
        return ""

    idx = int(hashlib.md5(str(chat_id).encode()).hexdigest(), 16) % len(suggestions)
    return f"\n\n\U0001f4a1 {suggestions[idx]}"


def _balance_line(credits: int | None) -> str:
    if credits is None:
        return ""
    return f"\n\n\U0001f4b0 Баланс: *{credits} образов*"


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
    credits = await _get_credit_balance(user_id)

    needs_upgrade = result.get("upgrade_prompt", False)
    hint = _retention_line(result, mode, chat_id)
    bal = _balance_line(credits)

    quality_warn = ""
    if result.get("quality_warning"):
        quality_warn = "\n\n\u2139\ufe0f Результат может отличаться от ожидаемого. Попробуй другой стиль или загрузи новое фото."

    footer = hint + quality_warn + bal

    if mode == "rating":
        await _send_rating(bot, chat_id, result, user_id, uname, quality_warn + bal)
    elif mode == "dating":
        await _send_dating(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade, footer)
    elif mode == "cv":
        await _send_cv(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade, footer)
    elif mode == "social":
        await _send_social(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade, footer)
    elif mode == "emoji":
        await _send_emoji(bot, chat_id, result, user_id, uname, gen_image_bytes, needs_upgrade, quality_warn + bal)
    else:
        kb = action_keyboard(uname, str(user_id))
        await bot.send_message(chat_id, f"Результат:\n```\n{result}\n```{bal}", parse_mode="Markdown", reply_markup=kb)


async def _send_rating(bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, footer: str):
    perception = result.get("perception", {})
    score = result.get("score", "?")
    trust = perception.get("trust", "?")
    attractiveness = perception.get("attractiveness", "?")
    emotion = perception.get("emotional_expression", "")

    insights = result.get("insights", [])
    recommendations = result.get("recommendations", [])

    text_parts = [
        f"\u2b50 *\u0420\u0435\u0439\u0442\u0438\u043d\u0433: {score}/10*\n",
        f"\u0414\u043e\u0432\u0435\u0440\u0438\u0435: {trust} | \u041f\u0440\u0438\u0432\u043b\u0435\u043a\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c: {attractiveness}",
        f"\u042d\u043c\u043e\u0446\u0438\u044f: {emotion}\n",
    ]

    if insights:
        text_parts.append(f"\U0001f4a1 {insights[0]}")
    if len(insights) > 1:
        text_parts.append(f"\U0001f4a1 {insights[1]}")

    if recommendations:
        text_parts.append(f"\n\U0001f3af {recommendations[0]}")

    text = "\n".join(text_parts) + footer
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


async def _send_dating(
    bot: Bot, chat_id: int, result: dict, user_id: int, uname: str,
    gen_image_bytes: bytes | None = None, needs_upgrade: bool = False, footer: str = "",
):
    score = result.get("dating_score", "?")
    impression = result.get("first_impression", "")
    strengths = result.get("strengths", [])

    enhancement = result.get("enhancement", {})
    style_name = enhancement.get("style", "")

    text_parts = [f"\U0001f495 *\u0414\u0435\u0439\u0442\u0438\u043d\u0433: {score}/10*\n"]

    if style_name:
        style_labels = {"warm_outdoor": "\u041d\u0430 \u043f\u0440\u043e\u0433\u0443\u043b\u043a\u0435", "studio_elegant": "\u0421\u0442\u0443\u0434\u0438\u044f", "cafe": "\u041a\u0430\u0444\u0435"}
        text_parts.append(f"\u0421\u0442\u0438\u043b\u044c: {style_labels.get(style_name, style_name)}")

    if impression:
        text_parts.append(f"\u0412\u043f\u0435\u0447\u0430\u0442\u043b\u0435\u043d\u0438\u0435: {impression[:120]}")

    if strengths:
        text_parts.append(f"\n\U0001f4aa {strengths[0]}")
    if len(strengths) > 1:
        text_parts.append(f"\U0001f4aa {strengths[1]}")

    delta = result.get("delta", {})
    if delta.get("dating_score"):
        d = delta["dating_score"]
        sign = "+" if d["delta"] >= 0 else ""
        text_parts.append(f"\n\U0001f4ca *\u0427\u0442\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u043e\u0441\u044c:* {sign}{d['delta']} \u043a \u043f\u0440\u0438\u0432\u043b\u0435\u043a\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u0438 ({d['pre']} \u2192 {d['post']})")

    if needs_upgrade:
        text_parts.append("\n\U0001f512 \u0423\u043b\u0443\u0447\u0448\u0435\u043d\u0438\u0435 \u043e\u0431\u0440\u0430\u0437\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u2014 \u043f\u043e\u043f\u043e\u043b\u043d\u0438 \u043f\u0430\u043a\u0435\u0442.")
    text = "\n".join(text_parts) + footer
    kb = upgrade_keyboard() if needs_upgrade else loop_keyboard(uname, str(user_id), "dating")
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="ratemeai_dating.jpg"),
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


async def _send_cv(
    bot: Bot, chat_id: int, result: dict, user_id: int, uname: str,
    gen_image_bytes: bytes | None = None, needs_upgrade: bool = False, footer: str = "",
):
    profession = result.get("profession", "?")
    trust = result.get("trust", "?")
    competence = result.get("competence", "?")
    hireability = result.get("hireability", "?")
    analysis = result.get("analysis", "")

    enhancement = result.get("enhancement", {})
    style_name = enhancement.get("style", "")

    text_parts = ["\U0001f4bc *\u041f\u0440\u043e\u0444\u0435\u0441\u0441\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0437*\n"]

    if style_name:
        style_labels = {"corporate": "\u041a\u043e\u0440\u043f\u043e\u0440\u0430\u0442\u0438\u0432\u043d\u044b\u0439", "creative": "\u041a\u0440\u0435\u0430\u0442\u0438\u0432\u043d\u044b\u0439", "neutral": "\u041d\u0435\u0439\u0442\u0440\u0430\u043b\u044c\u043d\u044b\u0439"}
        text_parts.append(f"\u0421\u0442\u0438\u043b\u044c: {style_labels.get(style_name, style_name)}")

    text_parts.extend([
        f"\u041f\u0440\u043e\u0444\u0435\u0441\u0441\u0438\u044f: {profession}",
        f"\u0414\u043e\u0432\u0435\u0440\u0438\u0435: {trust} | \u041a\u043e\u043c\u043f\u0435\u0442\u0435\u043d\u0442\u043d\u043e\u0441\u0442\u044c: {competence} | \u041d\u0430\u0439\u043c: {hireability}\n",
    ])

    if analysis:
        text_parts.append(f"\U0001f4dd {analysis[:200]}")

    delta = result.get("delta", {})
    if delta:
        delta_lines = []
        for key, label in [("trust", "\u0434\u043e\u0432\u0435\u0440\u0438\u0435"), ("competence", "\u043a\u043e\u043c\u043f\u0435\u0442\u0435\u043d\u0442\u043d\u043e\u0441\u0442\u044c"), ("hireability", "\u043d\u0430\u0439\u043c")]:
            d = delta.get(key)
            if d:
                sign = "+" if d["delta"] >= 0 else ""
                delta_lines.append(f"{label} {sign}{d['delta']}")
        if delta_lines:
            text_parts.append(f"\n\U0001f4ca *\u0427\u0442\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u043e\u0441\u044c:* {', '.join(delta_lines)}")

    if needs_upgrade:
        text_parts.append("\n\U0001f512 \u0423\u043b\u0443\u0447\u0448\u0435\u043d\u0438\u0435 \u043e\u0431\u0440\u0430\u0437\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u2014 \u043f\u043e\u043f\u043e\u043b\u043d\u0438 \u043f\u0430\u043a\u0435\u0442.")
    text = "\n".join(text_parts) + footer
    kb = upgrade_keyboard() if needs_upgrade else loop_keyboard(uname, str(user_id), "cv")
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="ratemeai_cv.jpg"),
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


async def _send_social(
    bot: Bot, chat_id: int, result: dict, user_id: int, uname: str,
    gen_image_bytes: bytes | None = None, needs_upgrade: bool = False, footer: str = "",
):
    first_impression = result.get("first_impression", "")
    social_score = result.get("social_score", "\u2014")
    strengths = result.get("strengths", [])
    weaknesses = result.get("weaknesses", [])
    style_name = result.get("style")

    text_parts = ["\U0001f4f8 *\u0421\u0442\u0438\u043b\u044c \u0434\u043b\u044f \u0441\u043e\u0446\u0441\u0435\u0442\u0435\u0439*\n"]

    if style_name:
        style_labels = {"influencer": "Influencer", "luxury": "Luxury", "casual": "Casual", "artistic": "Artistic"}
        text_parts.append(f"\u041e\u0431\u0440\u0430\u0437: {style_labels.get(style_name, style_name)}")

    if first_impression:
        text_parts.append(f"\u041f\u0435\u0440\u0432\u043e\u0435 \u0432\u043f\u0435\u0447\u0430\u0442\u043b\u0435\u043d\u0438\u0435: {first_impression[:200]}")

    text_parts.append(f"\u041e\u0446\u0435\u043d\u043a\u0430 \u0434\u043b\u044f \u0441\u043e\u0446\u0441\u0435\u0442\u0435\u0439: *{social_score}/10*\n")

    if strengths:
        text_parts.append("\u2705 \u0421\u0438\u043b\u044c\u043d\u044b\u0435 \u0441\u0442\u043e\u0440\u043e\u043d\u044b:")
        for s in strengths[:3]:
            text_parts.append(f"  \u2022 {s}")

    if weaknesses:
        text_parts.append("\n\U0001f4a1 \u0427\u0442\u043e \u043c\u043e\u0436\u043d\u043e \u0443\u043b\u0443\u0447\u0448\u0438\u0442\u044c:")
        for w in weaknesses[:2]:
            text_parts.append(f"  \u2022 {w}")

    delta = result.get("delta", {})
    if delta.get("social_score"):
        d = delta["social_score"]
        sign = "+" if d["delta"] >= 0 else ""
        text_parts.append(f"\n\U0001f4ca *\u0427\u0442\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u043e\u0441\u044c:* {sign}{d['delta']} ({d['pre']} \u2192 {d['post']})")

    if needs_upgrade:
        text_parts.append("\n\U0001f512 \u0423\u043b\u0443\u0447\u0448\u0435\u043d\u0438\u0435 \u043e\u0431\u0440\u0430\u0437\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u2014 \u043f\u043e\u043f\u043e\u043b\u043d\u0438 \u043f\u0430\u043a\u0435\u0442.")
    text = "\n".join(text_parts) + footer
    kb = upgrade_keyboard() if needs_upgrade else loop_keyboard(uname, str(user_id), "social")
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename="ratemeai_social.jpg"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=None if full_text else kb,
            )
            if full_text:
                await bot.send_message(chat_id, full_text, parse_mode="Markdown", reply_markup=kb)
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (social)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(bot, chat_id, img, caption=caption, reply_markup=kb, full_text=full_text):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_emoji(
    bot: Bot, chat_id: int, result: dict, user_id: int, uname: str,
    gen_image_bytes: bytes | None = None, needs_upgrade: bool = False, footer: str = "",
):
    base_desc = result.get("base_description", "")
    stickers = result.get("stickers", [])

    text_parts = ["\U0001f600 *\u042d\u043c\u043e\u0434\u0437\u0438-\u043f\u0430\u043a*\n"]
    if base_desc:
        text_parts.append(f"{base_desc[:150]}\n")

    if stickers:
        emoji_map = {
            "happy": "\U0001f60a", "sad": "\U0001f622", "angry": "\U0001f620", "surprised": "\U0001f632",
            "love": "\U0001f60d", "cool": "\U0001f60e", "thinking": "\U0001f914", "laughing": "\U0001f602",
            "sleepy": "\U0001f634", "wink": "\U0001f609", "scared": "\U0001f631", "party": "\U0001f389",
        }
        for s in stickers[:6]:
            emotion = s.get("emotion", "")
            icon = emoji_map.get(emotion, "\u2022")
            text_parts.append(f"{icon} {emotion}: {s.get('description', '')[:60]}")

    if needs_upgrade:
        text_parts.append("\n\U0001f512 \u0423\u043b\u0443\u0447\u0448\u0435\u043d\u0438\u0435 \u043e\u0431\u0440\u0430\u0437\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u2014 \u043f\u043e\u043f\u043e\u043b\u043d\u0438 \u043f\u0430\u043a\u0435\u0442.")
    text = "\n".join(text_parts) + footer
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
