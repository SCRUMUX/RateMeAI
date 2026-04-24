"""Result delivery — enhancement-first UX.

Photo is the primary focus. No visible scores in header.
Instead: current look description, fractional delta, and next-level suggestions.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from redis.asyncio import Redis

from src.bot.keyboards import post_result_keyboard, upgrade_keyboard, action_keyboard
from src.config import settings
from src.services.enhancement_advisor import build_enhancement_preview
from src.utils.text_sanitize import sanitize_llm_text
from src.utils.redis_keys import gen_image_cache_keys

logger = logging.getLogger(__name__)

_MAX_PHOTO_BYTES = 9 * 1024 * 1024
_MAX_CAPTION_LEN = 1024
_STORAGE_BASE = Path(settings.storage_local_path).resolve()


def _extract_storage_key(url_or_path: str) -> str | None:
    marker = "/storage/"
    idx = url_or_path.find(marker)
    if idx >= 0:
        return url_or_path[idx + len(marker) :]
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
            logger.warning(
                "send_photo by URL failed; trying httpx download", exc_info=True
            )

        if not sent:
            try:
                async with httpx.AsyncClient(
                    timeout=45.0, follow_redirects=True
                ) as client:
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
                logger.warning(
                    "httpx download failed; trying local filesystem", exc_info=True
                )

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
                    logger.exception(
                        "send_photo from local file failed: %s", local_path
                    )

    if not sent:
        logger.error("All photo delivery methods failed for: %s", url_or_path)
        return False

    if full_text:
        try:
            await bot.send_message(
                chat_id, full_text, parse_mode="Markdown", reply_markup=reply_markup
            )
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


async def _fetch_gen_image_from_redis(
    redis: Redis | None, task_id: str | None
) -> bytes | None:
    if not redis or not task_id:
        return None
    # Writers (edge/worker) scope the key by market_id after the geo-split refactor,
    # so we must probe both the scoped and legacy keys to stay compatible.
    candidate_keys = gen_image_cache_keys(task_id, settings.resolved_market_id)
    try:
        for cache_key in candidate_keys:
            b64 = await redis.get(cache_key)
            if not b64:
                continue
            try:
                await redis.delete(cache_key)
            except Exception:
                logger.debug(
                    "Failed to delete Redis key %s after read", cache_key, exc_info=True
                )
            data = base64.b64decode(b64)
            logger.info(
                "Loaded generated image from Redis for task %s via %s (%d bytes)",
                task_id,
                cache_key,
                len(data),
            )
            return data
    except Exception:
        logger.exception(
            "Failed to load generated image from Redis for task %s", task_id
        )
    return None


async def _get_credit_balance(
    user_id: int, redis: Redis | None = None, api_base_url: str = ""
) -> int | None:
    try:
        api_base = api_base_url or settings.api_base_url
        headers: dict[str, str] = {}
        if redis:
            from src.bot.handlers.mode_select import _get_api_headers

            headers = await _get_api_headers(redis, user_id, api_base)
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{api_base}/api/v1/payments/balance",
                headers=headers,
            )
        if resp.status_code == 200:
            return resp.json().get("image_credits")
    except Exception:
        logger.debug("Could not fetch balance for user %s", user_id)
    return None


def _format_score_val(val: float) -> str:
    """Always display with hundredths precision: 7.0 -> '7.00'."""
    return f"{val:.2f}"


def _format_delta_fractional(delta_val: float) -> str:
    if delta_val > 0:
        return f"+{delta_val:.2f}"
    return "+0.00"


def _build_next_level(
    mode: str,
    user_id: int,
    depth: int,
    current_style: str = "",
    used_styles: set[str] | None = None,
) -> tuple[str, list[dict]]:
    """Return (text, button_options) from the SAME picked styles."""
    preview = build_enhancement_preview(
        mode=mode,
        user_id=user_id,
        depth=depth,
        current_style=current_style,
        exclude=used_styles,
        count=2,
    )
    lines = ["\n\U0001f680 *Как усилить дальше:*"]
    for s in preview.suggestions[:2]:
        clean_line = sanitize_llm_text(s.line, max_len=200)
        if clean_line:
            lines.append(f"\u2022 {clean_line}")
    text = "\n".join(lines)

    options: list[dict] = []
    if preview.option_a:
        options.append(
            {
                "label": preview.option_a.label,
                "callback_data": preview.option_a.callback_data,
            }
        )
    if preview.option_b:
        options.append(
            {
                "label": preview.option_b.label,
                "callback_data": preview.option_b.callback_data,
            }
        )
    return text, options


def _balance_line(credits: int | None) -> str:
    if credits is None:
        return ""
    return f"\n\n\U0001f4b0 Баланс: *{credits} образов*"


def _no_image_reason_line(result: dict) -> str:
    """Return a short human-readable explanation when no image was produced.

    Mirrors the logic in ``web/src/context/AppContext.tsx`` so TG users
    and web users see the same semantics. Before v1.24.2 the bot silently
    delivered text-only results on generation errors, leaving users to
    guess why their photo didn't come back.
    """
    reason = str(result.get("no_image_reason") or "").strip()
    if not reason:
        return ""
    refunded = bool(result.get("credit_refunded"))
    refund_suffix = " Кредит возвращён." if refunded else ""

    diag_tail = ""
    raw_diag = result.get("image_gen_error_message")
    if isinstance(raw_diag, str):
        diag_tail = sanitize_llm_text(raw_diag, max_len=180).strip()

    if reason == "no_credits":
        return (
            "\n\n\u26a0\ufe0f Недостаточно кредитов для генерации изображения. "
            "Пополни баланс и попробуй снова."
        )
    if reason == "upgrade_required":
        return (
            "\n\n\U0001f512 Для генерации изображения необходимо пополнить баланс."
        )
    if reason == "not_applicable":
        return "\n\n\u2139\ufe0f Для данного режима генерация изображения недоступна."
    if reason == "generation_error":
        if diag_tail:
            return (
                f"\n\n\u26a0\ufe0f Не удалось сгенерировать изображение: "
                f"{diag_tail}.{refund_suffix}"
            )
        if refunded:
            return (
                "\n\n\u26a0\ufe0f Не удалось сгенерировать изображение. "
                "Кредит возвращён — попробуй другой стиль или фото."
            )
        return (
            "\n\n\u26a0\ufe0f Не удалось сгенерировать изображение. "
            "Попробуй другой стиль или фото."
        )
    return f"\n\n\u2139\ufe0f Анализ завершён без изображения ({reason})."


def _is_identity_risky(result: dict) -> bool:
    """Return True when the generated photo is flagged as low-similarity.

    Two independent signals raise the flag:
      * ``identity_unverified=True`` — quality-gate LLM call failed
        (e.g. Gemini returned non-dict JSON; see v1.14.2 fix). We cannot
        attest that the photo preserves identity, so we must be transparent.
      * ``enhancement.identity_match < 5.0`` — VLM scored the result below
        the soft threshold (``settings.identity_match_soft_threshold``).

    Kept in sync with the warnings emitted in
    ``src/orchestrator/executor.py::single_pass``.
    """
    if result.get("identity_unverified"):
        return True
    enh = result.get("enhancement") or {}
    try:
        score = float(enh.get("identity_match", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0
    # score == 0.0 is the "no comparison" case (no reference supplied);
    # strictly positive and below soft threshold is the real "low similarity".
    return 0.0 < score < settings.identity_match_soft_threshold


async def _send_identity_risk_prompt(bot: Bot, chat_id: int) -> None:
    """Ask the user whether to reupload or keep the risky result.

    Sent as a standalone follow-up message (the main image is already
    delivered) so the two paths remain orthogonal: "Accept" just dismisses
    the warning, "Reupload" clears photo cache and waits for a new file.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f4f7 Попробовать другое фото",
                    callback_data="reupload_photo",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\u2705 Оставить как есть",
                    callback_data="accept_risky_result",
                )
            ],
        ]
    )
    await bot.send_message(
        chat_id,
        "\u26a0\ufe0f *Сходство с оригиналом оказалось низким*\n\n"
        "Это бывает, когда на исходном фото видно только лицо крупным планом, "
        "а выбранный стиль требует полноростовой сцены. "
        "Можно загрузить другое фото (лучше — где видны плечи и корпус) "
        "или оставить текущий результат.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def deliver_result(
    bot: Bot,
    chat_id: int,
    status_msg_id: int,
    data: dict,
    user_id: int,
    redis: Redis | None = None,
    api_base_url: str = "",
):
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
    credits = await _get_credit_balance(user_id, redis, api_base_url=api_base_url)

    needs_upgrade = result.get("upgrade_prompt", False)
    bal = _balance_line(credits)

    gen_warnings = result.get("generation_warnings", [])
    if result.get("quality_warning"):
        gen_warnings.append(
            "Качество генерации может быть снижено. "
            "Загрузи более качественное исходное фото для лучшего результата."
        )
    quality_warn = ""
    if gen_warnings:
        quality_warn = "\n\n" + "\n".join(f"\u2139\ufe0f {w}" for w in gen_warnings[:3])

    # v1.24.2: surface the no-image reason to the TG user the same way
    # the web client does (see web/src/context/AppContext.tsx). Nothing
    # is appended when generation succeeded.
    no_image_line = ""
    if not result.get("generated_image_url") and not result.get("generated_image_b64"):
        no_image_line = _no_image_reason_line(result)
    quality_warn = quality_warn + no_image_line

    if mode == "rating":
        await _send_rating(bot, chat_id, result, user_id, uname, quality_warn + bal)
    elif mode == "dating":
        await _send_enhanced(
            bot,
            chat_id,
            result,
            user_id,
            uname,
            "dating",
            gen_image_bytes,
            needs_upgrade,
            quality_warn,
            bal,
            redis,
        )
    elif mode == "cv":
        await _send_enhanced(
            bot,
            chat_id,
            result,
            user_id,
            uname,
            "cv",
            gen_image_bytes,
            needs_upgrade,
            quality_warn,
            bal,
            redis,
        )
    elif mode == "social":
        await _send_enhanced(
            bot,
            chat_id,
            result,
            user_id,
            uname,
            "social",
            gen_image_bytes,
            needs_upgrade,
            quality_warn,
            bal,
            redis,
        )
    elif mode == "emoji":
        await _send_emoji(
            bot,
            chat_id,
            result,
            user_id,
            uname,
            gen_image_bytes,
            needs_upgrade,
            quality_warn + bal,
        )
    else:
        kb = action_keyboard(uname, str(user_id))
        await bot.send_message(
            chat_id,
            f"Результат:\n```\n{result}\n```{bal}",
            parse_mode="Markdown",
            reply_markup=kb,
        )

    if mode in ("dating", "cv", "social") and _is_identity_risky(result):
        try:
            await _send_identity_risk_prompt(bot, chat_id)
        except Exception:
            logger.warning(
                "Failed to send identity-risk prompt for task=%s",
                task_id,
                exc_info=True,
            )


async def _send_rating(
    bot: Bot, chat_id: int, result: dict, user_id: int, uname: str, footer: str
):
    """Rating mode — hidden, available via /rating."""
    perception = result.get("perception", {})
    score = result.get("score", "?")
    trust = perception.get("trust", "?")
    attractiveness = perception.get("attractiveness", "?")
    emotion = perception.get("emotional_expression", "")

    insights = result.get("insights", [])
    recommendations = result.get("recommendations", [])

    text_parts = [
        f"\u2b50 *Рейтинг: {score}/10*\n",
        f"Доверие: {trust} | Привлекательность: {attractiveness}",
        f"Эмоция: {emotion}\n",
    ]

    perception_block = _format_perception_breakdown(result)
    if perception_block:
        text_parts.append(perception_block)
        text_parts.append("")

    if insights:
        text_parts.append(f"\U0001f4a1 {insights[0]}")
    if len(insights) > 1:
        text_parts.append(f"\U0001f4a1 {insights[1]}")

    if recommendations:
        text_parts.append(f"\n\U0001f3af {recommendations[0]}")

    insights_text = _format_perception_insights(result)
    if insights_text:
        text_parts.append(f"\n{insights_text}")

    text = "\n".join(text_parts) + footer
    kb = post_result_keyboard("rating", str(user_id), uname)

    share_info = result.get("share", {})
    card_path = share_info.get("card_url")

    if card_path:
        caption, full_text = _split_caption(text)
        if await _send_photo_safe(
            bot,
            chat_id,
            card_path,
            caption=caption,
            reply_markup=kb,
            full_text=full_text,
        ):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _send_enhanced(
    bot: Bot,
    chat_id: int,
    result: dict,
    user_id: int,
    uname: str,
    mode: str,
    gen_image_bytes: bytes | None = None,
    needs_upgrade: bool = False,
    quality_warn: str = "",
    bal: str = "",
    redis: Redis | None = None,
):
    """Unified enhancement-first result for dating/cv/social."""

    mode_titles = {
        "dating": "\U0001f495 *Образ для знакомств*",
        "cv": "\U0001f4bc *Профессиональный образ*",
        "social": "\U0001f4f8 *Образ для соцсетей*",
    }

    text_parts = [mode_titles.get(mode, "\u2728 *Твой образ*")]

    impression = sanitize_llm_text(result.get("first_impression", ""), max_len=200)
    if impression:
        text_parts.append(f"\n{impression}")

    delta = result.get("delta", {})
    score_block = _format_score_block(mode, delta, result)
    if score_block:
        text_parts.append(f"\n{score_block}")

    depth = 2
    current_style = ""
    used_styles: set[str] = set()
    if redis:
        try:
            from src.bot.handlers.mode_select import (
                _get_depth,
                LAST_GEN_KEY,
                USED_STYLES_KEY,
            )

            depth = await _get_depth(redis, user_id, mode)
            depth = max(depth, 2)
            last = await redis.get(LAST_GEN_KEY.format(user_id))
            if last and ":" in last:
                current_style = last.split(":", 1)[1]
            raw_used = await redis.smembers(USED_STYLES_KEY.format(user_id, mode))
            if raw_used:
                used_styles = {
                    v if isinstance(v, str) else v.decode() for v in raw_used
                }
        except Exception:
            pass

    next_text, next_opts = _build_next_level(
        mode, user_id, depth, current_style, used_styles
    )
    text_parts.append(next_text)

    if needs_upgrade:
        text_parts.append(
            "\n\U0001f512 Улучшение образа недоступно \u2014 пополни пакет."
        )

    text_parts.append(quality_warn)
    text_parts.append(bal)

    text = "\n".join(text_parts)

    kb = (
        upgrade_keyboard()
        if needs_upgrade
        else post_result_keyboard(
            mode,
            str(user_id),
            uname,
            next_opts,
            current_style=current_style,
        )
    )
    caption, full_text = _split_caption(text)

    if gen_image_bytes:
        try:
            await bot.send_photo(
                chat_id,
                BufferedInputFile(gen_image_bytes, filename=f"ratemeai_{mode}.jpg"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=None if full_text else kb,
            )
            if full_text:
                await bot.send_message(
                    chat_id, full_text, parse_mode="Markdown", reply_markup=kb
                )
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (%s)", mode)

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(
            bot, chat_id, img, caption=caption, reply_markup=kb, full_text=full_text
        ):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


_PERCEPTION_ICONS = {
    "warmth": "\u2600\ufe0f",
    "presence": "\u26a1",
    "appeal": "\u2728",
    "authenticity": "\u2705",
}

_PERCEPTION_LABELS = {
    "warmth": "Теплота",
    "presence": "Уверенность",
    "appeal": "Привлекательность",
    "authenticity": "Аутентичность",
}


def _format_score_block(mode: str, delta: dict, result: dict) -> str:
    """Show composite score headline + perception breakdown + delta progression."""
    if mode == "cv":
        vals = [
            float(result.get(k, 0))
            for k in ("trust", "competence", "hireability")
            if result.get(k) is not None
        ]
        if not vals:
            return ""
        initial = round(sum(vals) / len(vals), 2)
    else:
        score_key = {"dating": "dating_score", "social": "social_score"}.get(mode)
        if not score_key or result.get(score_key) is None:
            return ""
        initial = float(result[score_key])

    parts: list[str] = []

    if delta:
        delta_lines = _format_delta_lines(mode, delta)
        if delta_lines:
            post_score = _compute_post_composite(mode, delta, initial)
            parts.append(
                f"\U0001f4ca *Твой скор: {_format_score_val(post_score)} / 10*"
            )
            parts.append("")
            parts.append(delta_lines)
        else:
            parts.append(f"\U0001f4ca *Твой скор: {_format_score_val(initial)} / 10*")
    else:
        parts.append(f"\U0001f4ca *Твой скор: {_format_score_val(initial)} / 10*")

    perception_block = _format_perception_breakdown(result)
    if perception_block:
        parts.append("")
        parts.append(perception_block)

    perception_delta = result.get("perception_delta", {})
    if perception_delta:
        pdelta_lines = _format_perception_delta(perception_delta)
        if pdelta_lines:
            parts.append("")
            parts.append(pdelta_lines)

    insights_text = _format_perception_insights(result)
    if insights_text:
        parts.append("")
        parts.append(insights_text)

    return "\n".join(parts)


def _format_perception_breakdown(result: dict) -> str:
    """Show current perception scores as a compact line."""
    ps = result.get("perception_scores", {})
    if hasattr(ps, "model_dump"):
        ps = ps.model_dump()
    if not ps:
        return ""

    items = []
    for key in ("warmth", "presence", "appeal"):
        val = ps.get(key)
        if val is not None:
            icon = _PERCEPTION_ICONS.get(key, "")
            label = _PERCEPTION_LABELS.get(key, key)
            items.append(f"{icon} {label}: {_format_score_val(float(val))}")

    auth = ps.get("authenticity")
    if auth is not None:
        items.append(f"\u2705 Аутентичность: {_format_score_val(float(auth))}")

    if not items:
        return ""
    return "*Профиль восприятия:*\n" + " \u2022 ".join(items)


def _format_perception_delta(perception_delta: dict) -> str:
    """Format perception parameter deltas."""
    lines = []
    for key in ("warmth", "presence", "appeal"):
        d = perception_delta.get(key)
        if d and d.get("delta", 0) > 0:
            icon = _PERCEPTION_ICONS.get(key, "")
            label = _PERCEPTION_LABELS.get(key, key)
            lines.append(_format_score_row(f"{icon} {label}", d))

    if not lines:
        return ""
    return "\u2728 *Что изменилось:*\n" + "\n".join(lines)


def _format_perception_insights(result: dict) -> str:
    """Show LLM-generated positive framing insights."""
    insights = result.get("perception_insights", [])
    if hasattr(insights, "__iter__") and not isinstance(insights, (str, dict)):
        pass
    else:
        return ""

    lines = []
    for item in insights[:2]:
        if isinstance(item, dict):
            suggestion = item.get("suggestion", "")
        elif hasattr(item, "suggestion"):
            suggestion = item.suggestion
        else:
            continue
        if suggestion:
            lines.append(f"\u2022 {suggestion[:120]}")

    if not lines:
        return ""
    return "\U0001f4a1 *Рекомендации:*\n" + "\n".join(lines)


def _compute_post_composite(mode: str, delta: dict, fallback: float) -> float:
    """Extract the post-score from delta dict for the header."""
    if mode == "cv":
        posts = [
            delta[k]["post"]
            for k in ("trust", "competence", "hireability")
            if k in delta and "post" in delta[k]
        ]
        return round(sum(posts) / len(posts), 2) if posts else fallback
    key = {"dating": "dating_score", "social": "social_score"}.get(mode)
    if key and key in delta and "post" in delta[key]:
        return delta[key]["post"]
    return fallback


def _format_delta_lines(mode: str, delta: dict) -> str:
    lines = []
    if mode == "dating" and delta.get("dating_score"):
        d = delta["dating_score"]
        if d.get("delta", 0) > 0:
            lines.append(_format_score_row("\U0001f495 Общий скор", d))
    elif mode == "cv":
        for key, label in [
            ("trust", "\U0001f91d Доверие"),
            ("competence", "\U0001f4a1 Компетентность"),
            ("hireability", "\U0001f4bc Найм"),
        ]:
            d = delta.get(key)
            if d and d.get("delta", 0) > 0:
                lines.append(_format_score_row(label, d))
    elif mode == "social" and delta.get("social_score"):
        d = delta["social_score"]
        if d.get("delta", 0) > 0:
            lines.append(_format_score_row("\U0001f4f8 Общий скор", d))

    if not lines:
        return ""
    return "\n".join(lines)


def _format_score_row(label: str, d: dict) -> str:
    pre = _format_score_val(d["pre"])
    post = _format_score_val(d["post"])
    delta_str = _format_delta_fractional(d["delta"])
    return f"\u25b2 {label}: {pre} \u2192 {post} *({delta_str})*"


async def _send_emoji(
    bot: Bot,
    chat_id: int,
    result: dict,
    user_id: int,
    uname: str,
    gen_image_bytes: bytes | None = None,
    needs_upgrade: bool = False,
    footer: str = "",
):
    base_desc = result.get("base_description", "")
    stickers = result.get("stickers", [])

    text_parts = ["\U0001f600 *Эмодзи-пак*\n"]
    if base_desc:
        text_parts.append(f"{base_desc[:150]}\n")

    if stickers:
        emoji_map = {
            "happy": "\U0001f60a",
            "sad": "\U0001f622",
            "angry": "\U0001f620",
            "surprised": "\U0001f632",
            "love": "\U0001f60d",
            "cool": "\U0001f60e",
            "thinking": "\U0001f914",
            "laughing": "\U0001f602",
            "sleepy": "\U0001f634",
            "wink": "\U0001f609",
            "scared": "\U0001f631",
            "party": "\U0001f389",
        }
        for s in stickers[:6]:
            emotion = s.get("emotion", "")
            icon = emoji_map.get(emotion, "\u2022")
            text_parts.append(f"{icon} {emotion}: {s.get('description', '')[:60]}")

    if needs_upgrade:
        text_parts.append(
            "\n\U0001f512 Улучшение образа недоступно \u2014 пополни пакет."
        )
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
                await bot.send_message(
                    chat_id, full_text, parse_mode="Markdown", reply_markup=kb
                )
            return
        except Exception:
            logger.exception("send_photo from Redis bytes failed (emoji)")

    img = result.get("generated_image_url") or result.get("image_url")
    if img:
        if await _send_photo_safe(
            bot, chat_id, img, caption=caption, reply_markup=kb, full_text=full_text
        ):
            return

    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
