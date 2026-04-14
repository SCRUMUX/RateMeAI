from __future__ import annotations

import io
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
import httpx
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY, get_bot_auth_headers
from src.bot.keyboards import (
    error_keyboard,
    scenario_keyboard,
    back_keyboard,
    style_keyboard,
    STYLE_CATALOG,
)
from src.services.enhancement_advisor import build_enhancement_preview

logger = logging.getLogger(__name__)
router = Router()
PRE_ANALYSIS_REF_KEY = "ratemeai:preanalysis_ref:{}"

LAST_GEN_KEY = "ratemeai:last_gen:{}"
USED_STYLES_KEY = "ratemeai:used_styles:{}:{}"

def _build_display_names() -> dict[str, dict[str, str]]:
    """Build display name mapping from STYLE_CATALOG, stripping emoji prefixes."""
    result: dict[str, dict[str, str]] = {}
    for mode, items in STYLE_CATALOG.items():
        mapping: dict[str, str] = {}
        for key, label, _hook, *_rest in items:
            clean = label.lstrip()
            parts = clean.split(" ", 1)
            mapping[key] = parts[1] if len(parts) > 1 else parts[0]
        result[mode] = mapping
    return result


_STYLE_DISPLAY_NAMES: dict[str, dict[str, str]] = _build_display_names()
_PROCESSING_LOCK = "ratemeai:processing:{}"
_LOCK_TTL = 300
DEPTH_KEY = "ratemeai:depth:{}:{}"

# Task polling (_poll_task): must cover worker latency + DB commit lag + slow image gen (Replicate).
# When Redis publishes task_done, we only need to wait until GET /tasks returns completed — often a few
# extra seconds; 3 HTTP retries was too few and showed "too long" while credits were already deducted.
_PUBSUB_ITERATIONS = 180
_POLL_MAX_IF_NOTIFIED = 45
_POLL_MAX_IF_NOT_NOTIFIED = 70
_POLL_SLEEP_NOTIFIED = 1.0
_POLL_SLEEP_FALLBACK = 3.0


@router.callback_query(F.data.startswith("pick_style:"))
async def on_pick_style(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Call pre-analyze, show scores + perception profile + style suggestions."""
    kind = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return
    await callback.answer()

    if kind not in ("dating", "cv", "social"):
        await callback.message.answer("Выбери направление:", reply_markup=scenario_keyboard())
        return

    mode_headers = {
        "dating": "\U0001f495 *Образ для знакомств*",
        "cv": "\U0001f4bc *Профессиональный образ*",
        "social": "\U0001f4f8 *Образ для соцсетей*",
    }
    header = mode_headers.get(kind, "\u2728 *Твой образ*")

    status_msg = await callback.message.answer(f"{header}\n\n\U0001f50d Анализирую твоё фото...")

    pre_analysis = await _call_pre_analyze(callback.bot, api_base_url, user_id, file_id, kind, redis)

    if pre_analysis is None:
        catalog = STYLE_CATALOG.get(kind, [])
        hooks = [f"\u2022 {label} \u2014 {hook}" for _key, label, hook, *_rest in catalog[:3]]
        text = (
            f"{header}\n\n"
            "\U0001f680 *Что можно усилить:*\n"
            + "\n".join(hooks)
            + "\n\n*Выбери стиль:*"
        )
        try:
            await status_msg.edit_text(text, parse_mode="Markdown", reply_markup=style_keyboard(kind))
        except Exception:
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=style_keyboard(kind))
        return

    pre_id = pre_analysis.get("pre_analysis_id", "")
    if pre_id:
        await redis.set(PRE_ANALYSIS_REF_KEY.format(user_id), pre_id, ex=1800)

    text = _format_pre_analysis_message(header, kind, user_id, pre_analysis)

    try:
        await status_msg.edit_text(text, parse_mode="Markdown", reply_markup=style_keyboard(kind))
    except Exception:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=style_keyboard(kind))


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """User picked a style — run the pipeline immediately."""
    parts = callback.data.split(":")
    mode = parts[1]
    style = parts[2] if len(parts) > 2 else ""
    await _submit_analysis(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data.startswith("enhance:"))
async def on_enhancement_choice(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """User picked a binary option — run the full pipeline."""
    parts = callback.data.split(":")
    mode = parts[1]
    style = parts[2] if len(parts) > 2 else ""
    await _submit_analysis(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data.startswith("mode:"))
async def on_mode_selected(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Legacy: direct mode selection (for /rating command flow)."""
    mode = callback.data.split(":", 1)[1]
    await _submit_analysis(callback, api_base_url, redis, mode, "")


@router.callback_query(F.data.startswith("restyle:"))
async def on_restyle(callback: CallbackQuery, redis: Redis):
    """Show style keyboard for current mode."""
    mode = callback.data.split(":", 1)[1]
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Фото больше не доступно. Отправь новое!", show_alert=True)
        return
    await callback.answer()
    mode_headers = {
        "dating": "\U0001f495 Выбери образ:",
        "cv": "\U0001f4bc Выбери образ:",
        "social": "\U0001f4f8 Выбери образ:",
    }
    header = mode_headers.get(mode)
    if header:
        await callback.message.answer(header, reply_markup=style_keyboard(mode))
    else:
        await callback.message.answer("Выбери направление:", reply_markup=scenario_keyboard())


@router.callback_query(F.data.startswith("styles_page:"))
async def on_styles_page(callback: CallbackQuery):
    """Paginate through style options."""
    parts = callback.data.split(":")
    mode = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=style_keyboard(mode, page))
    except Exception:
        await callback.message.answer("Выбери стиль:", reply_markup=style_keyboard(mode, page))


@router.callback_query(F.data == "retry")
async def on_retry(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Retry last generation using stored context."""
    user_id = callback.from_user.id
    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Фото больше не доступно. Отправь новое!", show_alert=True)
        return
    last = await redis.get(LAST_GEN_KEY.format(user_id))
    if last and ":" in last:
        mode, style = last.split(":", 1)
    else:
        await callback.answer()
        await callback.message.answer("Выбери направление:", reply_markup=scenario_keyboard())
        return
    await _submit_analysis(callback, api_base_url, redis, mode, style)


async def _call_pre_analyze(bot, api_base_url: str, user_id: int, file_id: str, mode: str, redis: Redis) -> dict | None:
    """Download the user's photo and call POST /api/v1/pre-analyze. Returns response dict or None on failure."""
    try:
        if isinstance(file_id, bytes):
            file_id = file_id.decode()
        file_obj = await bot.get_file(file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file_obj.file_path, file_bytes)
        file_bytes.seek(0)
        image_data = file_bytes.read()

        headers = await get_bot_auth_headers(redis, user_id)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/pre-analyze",
                files={"image": ("photo.jpg", image_data, "image/jpeg")},
                data={"mode": mode},
                headers=headers,
            )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("pre-analyze returned %s: %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("pre-analyze call failed for user %s", user_id)
    return None


def _format_pre_analysis_message(header: str, kind: str, user_id: int, data: dict) -> str:
    """Format the pre-analysis scores + suggestions into a Telegram message."""
    first_impression = data.get("first_impression", "")
    score = data.get("score", 0)
    ps = data.get("perception_scores", {})

    lines = [header]
    if first_impression:
        lines.append(first_impression)
    lines.append("")
    lines.append(f"\U0001f4ca *Твой скор: {score:.2f} / 10*")
    lines.append("")

    warmth = ps.get("warmth", 0)
    presence = ps.get("presence", 0)
    appeal = ps.get("appeal", 0)
    lines.append("*Профиль восприятия:*")
    lines.append(
        f"\u2600\ufe0f Теплота: {warmth:.2f} \u2022 "
        f"\u26a1 Уверенность: {presence:.2f} \u2022 "
        f"\u2728 Привлекательность: {appeal:.2f}"
    )

    opportunities = data.get("enhancement_opportunities", [])
    if opportunities:
        lines.append("")
        lines.append("\U0001f4a1 *Рекомендации:*")
        for opp in opportunities[:3]:
            lines.append(f"\u2022 {opp}")

    preview = build_enhancement_preview(kind, user_id, depth=1, count=3)
    if preview.suggestions:
        lines.append("")
        lines.append("\U0001f680 *Как усилить:*")
        for s in preview.suggestions[:3]:
            lines.append(f"\u2022 {s.line}")

    lines.append("")
    lines.append("*Выбери стиль:*")
    return "\n".join(lines)


async def _submit_analysis(callback: CallbackQuery, api_base_url: str, redis: Redis, mode: str, style: str):
    from src.config import settings as _settings
    user_id = callback.from_user.id
    bot = callback.bot
    analyze_api = _settings.edge_api_url.rstrip("/") if _settings.edge_api_url else api_base_url

    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return

    lock_key = _PROCESSING_LOCK.format(user_id)
    acquired = await redis.set(lock_key, "1", ex=_LOCK_TTL, nx=True)
    if not acquired:
        await callback.answer("\u23f3 Предыдущий запрос ещё обрабатывается...", show_alert=True)
        return

    await callback.answer()

    depth = await _get_depth(redis, user_id, mode)
    if depth > 1:
        status_text = f"\u23f3 Усиливаю образ (уровень {depth})\u2026 Это может занять до минуты."
    else:
        status_text = "\u23f3 Улучшаю твой образ\u2026 Это может занять до минуты."
    status_msg = await callback.message.answer(status_text)

    await redis.set(LAST_GEN_KEY.format(user_id), f"{mode}:{style}", ex=86400)
    if style:
        used_key = USED_STYLES_KEY.format(user_id, mode)
        await redis.sadd(used_key, style)
        await redis.expire(used_key, 86400)
    await _increment_depth(redis, user_id, mode)

    try:
        file = await bot.get_file(file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)
        image_data = file_bytes.read()

        from src.orchestrator.enhancement_matrix import level_for_depth
        enh_level = level_for_depth(depth).level

        form_data = {"mode": mode, "enhancement_level": str(enh_level)}
        if style:
            form_data["style"] = style

        pre_id = await redis.get(PRE_ANALYSIS_REF_KEY.format(user_id))
        if pre_id:
            if isinstance(pre_id, bytes):
                pre_id = pre_id.decode()
            form_data["pre_analysis_id"] = pre_id

        auth_headers = await get_bot_auth_headers(redis, user_id)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{analyze_api}/api/v1/analyze",
                files={"image": ("photo.jpg", image_data, "image/jpeg")},
                data=form_data,
                headers=auth_headers,
            )

        if resp.status_code == 202:
            task_data = resp.json()
            task_id = task_data["task_id"]

            if not hasattr(bot, "_pending_tasks"):
                bot._pending_tasks = {}
            bot._pending_tasks[user_id] = {
                "task_id": task_id,
                "chat_id": callback.message.chat.id,
                "status_msg_id": status_msg.message_id,
            }

            import asyncio
            asyncio.create_task(_poll_task(bot, analyze_api, user_id, task_id, callback.message.chat.id, status_msg.message_id, redis))

        elif resp.status_code == 429:
            await redis.delete(lock_key)
            await status_msg.edit_text(
                "\u26a0\ufe0f Дневной лимит исчерпан. Попробуй завтра!",
                reply_markup=error_keyboard(),
            )
        else:
            await redis.delete(lock_key)
            detail = resp.json().get("detail", "Unknown error")
            await status_msg.edit_text(f"\u274c Ошибка: {detail}", reply_markup=error_keyboard())

    except Exception:
        await redis.delete(lock_key)
        logger.exception("Failed to submit analysis for user %s", user_id)
        await status_msg.edit_text("\u274c Произошла ошибка. Попробуй позже.", reply_markup=error_keyboard())


@router.callback_query(F.data.startswith("buy:"))
async def on_buy(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Create YooKassa payment via edge server API and send payment link."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from src.config import settings

    pack_qty = int(callback.data.split(":", 1)[1])

    await callback.answer()
    wait_msg = await callback.message.answer("\U0001f4b3 Создаю платёж...")

    tg_id = callback.from_user.id
    payment_api = settings.edge_api_url.rstrip("/") if settings.edge_api_url else api_base_url

    try:
        session_token = await _ensure_edge_session(
            redis, tg_id, callback.from_user.username,
            callback.from_user.first_name, payment_api,
        )
        if not session_token:
            await wait_msg.edit_text(
                "\u274c Не удалось создать профиль для оплаты. Попробуй /start.",
                reply_markup=error_keyboard(),
            )
            return

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{payment_api}/api/v1/payments/create",
                json={"pack_qty": pack_qty},
                headers={"Authorization": f"Bearer {session_token}"},
            )

        if resp.status_code != 200:
            detail = resp.json().get("detail", "unknown error") if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:200]
            logger.error("Payment create failed on %s: %s %s", payment_api, resp.status_code, detail)
            await wait_msg.edit_text(
                "\u274c Не удалось создать платёж. Попробуй позже.",
                reply_markup=error_keyboard(),
            )
            return

        data = resp.json()
        confirmation_url = data["confirmation_url"]

        from src.services.payments import _pack_by_quantity
        pack = _pack_by_quantity(pack_qty)
        price_label = f"{pack.price_rub} \u20bd" if pack else f"{pack_qty} образов"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"\U0001f4b3 Оплатить {price_label}", url=confirmation_url)],
            [InlineKeyboardButton(text="\U0001f4b0 Проверить баланс", callback_data="balance")],
            [InlineKeyboardButton(text="\U0001f4f8 Новое фото", callback_data="new_photo")],
        ])
        qty_label = pack.quantity if pack else pack_qty
        await wait_msg.edit_text(
            f"\U0001f6d2 *Пакет: {qty_label} образов за {price_label}*\n\n"
            f"Нажми кнопку ниже для оплаты.\n"
            f"После оплаты образы зачислятся автоматически!",
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Failed to create payment for tg_user=%s", tg_id)
        await wait_msg.edit_text(
            "\u274c Не удалось создать платёж. Попробуй позже.",
            reply_markup=error_keyboard(),
        )


@router.callback_query(F.data == "balance")
async def on_balance(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Show user's current credit balance (from edge server where payments are processed)."""
    from src.config import settings
    await callback.answer()
    user_id = callback.from_user.id
    payment_api = settings.edge_api_url.rstrip("/") if settings.edge_api_url else api_base_url

    try:
        token = await _ensure_edge_session(
            redis, user_id, callback.from_user.username,
            callback.from_user.first_name, payment_api,
        )
        headers = {"Authorization": f"Bearer {token}"} if token else await get_bot_auth_headers(redis, user_id)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{payment_api}/api/v1/payments/balance",
                headers=headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            credits = data.get("image_credits", 0)
            text = (
                f"\U0001f4b0 *Твой баланс*\n\n"
                f"Доступно образов: *{credits}*\n\n"
            )
            if credits == 0:
                text += "Открой новые образы и стили!"
                from src.bot.keyboards import upgrade_keyboard
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=upgrade_keyboard())
            else:
                text += "Отправь фото для улучшения образа!"
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            await callback.message.answer("\u274c Не удалось получить баланс.", reply_markup=error_keyboard())
    except Exception:
        logger.exception("Failed to fetch balance for user %s", user_id)
        await callback.message.answer("\u274c Ошибка. Попробуй позже.", reply_markup=error_keyboard())


@router.callback_query(F.data == "topup")
async def on_topup(callback: CallbackQuery):
    """Show available credit packs for purchase."""
    await callback.answer()
    from src.bot.keyboards import upgrade_keyboard
    await callback.message.answer(
        "\U0001f6d2 *Пополнить баланс*\n\n"
        "Выбери подходящий пакет образов:",
        parse_mode="Markdown",
        reply_markup=upgrade_keyboard(),
    )


@router.callback_query(F.data == "new_photo")
async def on_new_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("\U0001f4f8 Отправь мне новое фото!", reply_markup=back_keyboard())


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _resolve_user_id(api_base_url: str, telegram_id: int) -> str | None:
    """Get internal UUID user_id for a Telegram user."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/auth/telegram",
                json={"telegram_id": telegram_id},
            )
        if resp.status_code == 200:
            return resp.json().get("user_id")
    except Exception:
        logger.debug("Could not resolve user_id for tg=%s", telegram_id)
    return None


_EDGE_SESSION_KEY = "bot_edge_session:{}"
_EDGE_SESSION_TTL = 86400 * 7


async def _ensure_edge_session(
    redis: Redis, telegram_id: int, username: str | None,
    first_name: str | None, edge_url: str,
) -> str | None:
    """Get or create a session token on the edge server for this Telegram user."""
    cached = await redis.get(_EDGE_SESSION_KEY.format(telegram_id))
    if cached:
        return cached.decode() if isinstance(cached, bytes) else cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{edge_url}/api/v1/auth/telegram",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("session_token")
            if token:
                await redis.set(
                    _EDGE_SESSION_KEY.format(telegram_id), token, ex=_EDGE_SESSION_TTL,
                )
                return token
    except Exception:
        logger.exception("Failed to get edge session for tg=%s on %s", telegram_id, edge_url)
    return None


# ------------------------------------------------------------------
# Depth tracking
# ------------------------------------------------------------------

async def _get_depth(redis: Redis, user_id: int, mode: str) -> int:
    key = DEPTH_KEY.format(user_id, mode)
    val = await redis.get(key)
    return int(val) if val else 1


async def _increment_depth(redis: Redis, user_id: int, mode: str) -> int:
    key = DEPTH_KEY.format(user_id, mode)
    new_val = await redis.incr(key)
    await redis.expire(key, 86400)
    return new_val


# ------------------------------------------------------------------
# Progress streaming
# ------------------------------------------------------------------

async def _update_progress(bot, chat_id: int, status_msg_id: int, data_str: str):
    """Update the status message with step progress."""
    try:
        parts = data_str.split(":")
        step_raw = parts[0] if parts else ""
        current = int(parts[1]) if len(parts) > 1 else 0
        total = int(parts[2]) if len(parts) > 2 else 0

        step_name = step_raw.split("_", 2)[-1] if step_raw.startswith("step_") else step_raw
        label = _STEP_LABELS.get(step_name, f"Шаг {current}...")
        bar = "\u2593" * current + "\u2591" * (total - current)
        text = f"\u23f3 {label}\n[{bar}] {current}/{total}"

        await bot.edit_message_text(text, chat_id=chat_id, message_id=status_msg_id)
    except Exception:
        pass


_STEP_LABELS: dict[str, str] = {
    "background_edit": "Работаю над окружением\u2026",
    "lighting_adjust": "Улучшаю освещение\u2026",
    "clothing_edit": "Подбираю стиль одежды\u2026",
    "expression_hint": "Работаю с выражением\u2026",
    "skin_correction": "Сохраняю идентичность\u2026",
    "style_overall": "Финализация образа\u2026",
    "preprocess": "Анализ черт лица\u2026",
    "analyze": "Подбираю улучшения\u2026",
    "identity": "Сохраняю идентичность\u2026",
}


# ------------------------------------------------------------------
# Task polling
# ------------------------------------------------------------------

async def _poll_task(bot, api_base_url: str, user_id: int, task_id: str, chat_id: int, status_msg_id: int, redis: Redis):
    """Wait for task via Redis Pub/Sub, with HTTP polling fallback."""
    import asyncio
    from src.bot.handlers.results import deliver_result

    lock_key = _PROCESSING_LOCK.format(user_id)

    done_channel = f"ratemeai:task_done:{task_id}"
    progress_channel = f"ratemeai:progress:{task_id}"
    notified = False

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(done_channel, progress_channel)
        try:
            for _ in range(_PUBSUB_ITERATIONS):
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    ch = msg.get("channel", "")
                    if isinstance(ch, bytes):
                        ch = ch.decode()
                    if ch == done_channel:
                        notified = True
                        break
                    if ch == progress_channel:
                        data_str = msg.get("data", "")
                        if isinstance(data_str, bytes):
                            data_str = data_str.decode()
                        await _update_progress(bot, chat_id, status_msg_id, data_str)
        finally:
            await pubsub.unsubscribe(done_channel, progress_channel)
            await pubsub.close()
    except Exception:
        logger.warning("Pub/Sub failed for task %s, falling back to polling", task_id)

    async def _fetch_task_status():
        auth_headers = await get_bot_auth_headers(redis, user_id)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/tasks/{task_id}",
                headers=auth_headers,
            )
            if resp.status_code != 200:
                return None
            return resp.json()

    max_polls = _POLL_MAX_IF_NOTIFIED if notified else _POLL_MAX_IF_NOT_NOTIFIED
    sleep_interval = _POLL_SLEEP_NOTIFIED if notified else _POLL_SLEEP_FALLBACK

    last_status: str | None = None
    for attempt in range(max_polls):
        if not notified:
            await asyncio.sleep(sleep_interval)
        try:
            data = await _fetch_task_status()
            if data is None:
                if notified:
                    await asyncio.sleep(_POLL_SLEEP_NOTIFIED)
                continue

            status = data.get("status")
            if status is not None:
                last_status = status

            if status == "completed":
                await redis.delete(lock_key)
                await deliver_result(bot, chat_id, status_msg_id, data, user_id, redis, api_base_url=api_base_url)
                return
            if status == "failed":
                await redis.delete(lock_key)
                await bot.edit_message_text(
                    "\u274c Не удалось обработать фото. Попробуй загрузить другое фото.",
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    reply_markup=error_keyboard(),
                )
                return

        except Exception:
            logger.exception("Poll error for task %s", task_id)

        if notified:
            await asyncio.sleep(_POLL_SLEEP_NOTIFIED)

    # Grace window: task may commit to DB right after last poll (race with worker).
    for _ in range(3):
        await asyncio.sleep(2.0)
        try:
            data = await _fetch_task_status()
            if data and data.get("status") is not None:
                last_status = data.get("status")
            if data and data.get("status") == "completed":
                await redis.delete(lock_key)
                await deliver_result(bot, chat_id, status_msg_id, data, user_id, redis, api_base_url=api_base_url)
                return
            if data and data.get("status") == "failed":
                await redis.delete(lock_key)
                await bot.edit_message_text(
                    "\u274c Не удалось обработать фото. Попробуй загрузить другое фото.",
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    reply_markup=error_keyboard(),
                )
                return
        except Exception:
            logger.exception("Grace poll error for task %s", task_id)

    logger.warning(
        "Task poll timeout task_id=%s user_id=%s last_status=%s redis_notified=%s",
        task_id,
        user_id,
        last_status,
        notified,
    )
    await redis.delete(lock_key)
    await bot.edit_message_text(
        "\u23f0 Обработка занимает слишком долго. Попробуй позже или проверь /balance — "
        "результат мог прийти с задержкой.",
        chat_id=chat_id,
        message_id=status_msg_id,
        reply_markup=error_keyboard(),
    )
