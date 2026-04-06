from __future__ import annotations

import io
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
import httpx
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY
from src.bot.keyboards import (
    dating_style_keyboard,
    cv_style_keyboard,
    social_style_keyboard,
    enhancement_choice_keyboard,
    error_keyboard,
    scenario_keyboard,
    back_keyboard,
)
from src.services.enhancement_advisor import build_enhancement_preview

logger = logging.getLogger(__name__)
router = Router()

LAST_GEN_KEY = "ratemeai:last_gen:{}"
_PROCESSING_LOCK = "ratemeai:processing:{}"
_LOCK_TTL = 60
DEPTH_KEY = "ratemeai:depth:{}:{}"


@router.callback_query(F.data.startswith("pick_style:"))
async def on_pick_style(callback: CallbackQuery, redis: Redis):
    """Show style selection keyboard for scenario."""
    kind = callback.data.split(":", 1)[1]
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return
    await callback.answer()
    if kind == "dating":
        await callback.message.answer("\U0001f495 Выбери образ:", reply_markup=dating_style_keyboard())
    elif kind == "social":
        await callback.message.answer("\U0001f4f8 Выбери образ:", reply_markup=social_style_keyboard())
    elif kind == "cv":
        await callback.message.answer("\U0001f4bc Выбери образ:", reply_markup=cv_style_keyboard())
    else:
        await callback.message.answer("Выбери направление:", reply_markup=scenario_keyboard())


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, redis: Redis):
    """Show Enhancement Preview with predictions + 2 binary options."""
    parts = callback.data.split(":")
    mode = parts[1]
    style = parts[2] if len(parts) > 2 else ""
    user_id = callback.from_user.id

    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return
    await callback.answer()

    depth = await _get_depth(redis, user_id, mode)

    preview = build_enhancement_preview(
        mode=mode,
        analysis_result={},
        user_id=user_id,
        depth=depth,
        current_style=style,
    )

    text = (
        "\u2728 *Давай усилим образ*\n\n"
        "Можно улучшить через:\n"
        f"{preview.suggestions_text}\n\n"
        "Выбери направление:"
    )

    kb = enhancement_choice_keyboard(
        option_a_label=preview.option_a.label,
        option_a_data=f"enhance:{mode}:{preview.option_a.key}",
        option_b_label=preview.option_b.label,
        option_b_data=f"enhance:{mode}:{preview.option_b.key}",
    )

    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


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


@router.callback_query(F.data.startswith("action:"))
async def on_action(callback: CallbackQuery, redis: Redis):
    """Reuse stored photo for a different scenario."""
    mode = callback.data.split(":", 1)[1]
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Фото больше не доступно. Отправь новое!", show_alert=True)
        return
    await callback.answer()
    if mode == "dating":
        await callback.message.answer("\U0001f495 Выбери образ:", reply_markup=dating_style_keyboard())
    elif mode == "cv":
        await callback.message.answer("\U0001f4bc Выбери образ:", reply_markup=cv_style_keyboard())
    elif mode == "social":
        await callback.message.answer("\U0001f4f8 Выбери образ:", reply_markup=social_style_keyboard())
    else:
        await callback.message.answer("Выбери направление:", reply_markup=scenario_keyboard())


@router.callback_query(F.data.startswith("loop:"))
async def on_loop(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Re-generate with a different personality/style, same photo."""
    parts = callback.data.split(":")
    mode = parts[1]
    style = parts[2] if len(parts) > 2 else ""
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Фото больше не доступно. Отправь новое!", show_alert=True)
        return
    await _submit_analysis(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data.startswith("restyle:"))
async def on_restyle(callback: CallbackQuery, redis: Redis):
    """Show style keyboard for current mode."""
    mode = callback.data.split(":", 1)[1]
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Фото больше не доступно. Отправь новое!", show_alert=True)
        return
    await callback.answer()
    if mode == "dating":
        await callback.message.answer("\U0001f495 Выбери образ:", reply_markup=dating_style_keyboard())
    elif mode == "cv":
        await callback.message.answer("\U0001f4bc Выбери образ:", reply_markup=cv_style_keyboard())
    elif mode == "social":
        await callback.message.answer("\U0001f4f8 Выбери образ:", reply_markup=social_style_keyboard())
    else:
        await callback.message.answer("Выбери направление:", reply_markup=scenario_keyboard())


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


async def _submit_analysis(callback: CallbackQuery, api_base_url: str, redis: Redis, mode: str, style: str):
    user_id = callback.from_user.id
    bot = callback.bot

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

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/analyze",
                files={"image": ("photo.jpg", image_data, "image/jpeg")},
                data=form_data,
                headers={"X-Telegram-Id": str(user_id)},
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
            asyncio.create_task(_poll_task(bot, api_base_url, user_id, task_id, callback.message.chat.id, status_msg.message_id, redis))

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
async def on_buy(callback: CallbackQuery):
    """Create YooKassa payment and send payment link."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from src.services.payments import create_payment, _pack_by_quantity

    pack_qty = int(callback.data.split(":", 1)[1])
    pack = _pack_by_quantity(pack_qty)
    if not pack:
        await callback.answer("Неизвестный пакет", show_alert=True)
        return

    await callback.answer()
    wait_msg = await callback.message.answer("\U0001f4b3 Создаю платёж...")

    result = await create_payment(callback.from_user.id, pack_qty)
    if result is None:
        await wait_msg.edit_text(
            "\u274c Не удалось создать платёж. Попробуй позже.",
            reply_markup=error_keyboard(),
        )
        return

    _payment_id, confirmation_url = result
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"\U0001f4b3 Оплатить {pack.price_rub} \u20bd", url=confirmation_url)],
        [InlineKeyboardButton(text="\U0001f4b0 Проверить баланс", callback_data="balance")],
        [InlineKeyboardButton(text="\U0001f4f8 Новое фото", callback_data="new_photo")],
    ])
    await wait_msg.edit_text(
        f"\U0001f6d2 *Пакет: {pack.quantity} образов за {pack.price_rub} \u20bd*\n\n"
        f"Нажми кнопку ниже для оплаты.\n"
        f"После оплаты образы зачислятся автоматически!",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@router.callback_query(F.data == "balance")
async def on_balance(callback: CallbackQuery, api_base_url: str):
    """Show user's current credit balance."""
    await callback.answer()
    user_id = callback.from_user.id
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/payments/balance",
                headers={"X-Telegram-Id": str(user_id)},
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


@router.callback_query(F.data == "new_photo")
async def on_new_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("\U0001f4f8 Отправь мне новое фото!", reply_markup=back_keyboard())


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
            for _ in range(120):
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

    async with httpx.AsyncClient(timeout=15.0) as client:
        max_polls = 3 if notified else 30
        sleep_interval = 1 if notified else 3

        for attempt in range(max_polls):
            if not notified:
                await asyncio.sleep(sleep_interval)
            try:
                resp = await client.get(
                    f"{api_base_url}/api/v1/tasks/{task_id}",
                    headers={"X-Telegram-Id": str(user_id)},
                )
                if resp.status_code != 200:
                    if notified:
                        await asyncio.sleep(1)
                    continue

                data = resp.json()
                status = data.get("status")

                if status == "completed":
                    await redis.delete(lock_key)
                    await deliver_result(bot, chat_id, status_msg_id, data, user_id, redis)
                    return
                elif status == "failed":
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
                await asyncio.sleep(1)

        await redis.delete(lock_key)
        await bot.edit_message_text(
            "\u23f0 Обработка занимает слишком долго. Попробуй позже.",
            chat_id=chat_id,
            message_id=status_msg_id,
            reply_markup=error_keyboard(),
        )
