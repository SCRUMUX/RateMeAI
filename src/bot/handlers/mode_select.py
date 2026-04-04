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
    error_keyboard,
    mode_selection_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

LAST_GEN_KEY = "ratemeai:last_gen:{}"


@router.callback_query(F.data.startswith("pick_style:"))
async def on_pick_style(callback: CallbackQuery, redis: Redis):
    """Show style selection keyboard for dating/cv modes."""
    kind = callback.data.split(":", 1)[1]
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return
    await callback.answer()
    if kind == "dating":
        await callback.message.answer("💕 Выбери стиль фото:", reply_markup=dating_style_keyboard())
    else:
        await callback.message.answer("💼 Выбери стиль фото:", reply_markup=cv_style_keyboard())


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Handle style:dating:warm_outdoor → submit analysis with context."""
    parts = callback.data.split(":")
    mode = parts[1]
    style = parts[2] if len(parts) > 2 else ""
    await _submit_analysis(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data.startswith("mode:"))
async def on_mode_selected(callback: CallbackQuery, api_base_url: str, redis: Redis):
    mode = callback.data.split(":", 1)[1]
    await _submit_analysis(callback, api_base_url, redis, mode, "")


@router.callback_query(F.data.startswith("action:"))
async def on_action(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Reuse stored photo for a different mode (no re-upload)."""
    mode = callback.data.split(":", 1)[1]
    file_id = await redis.get(PHOTO_KEY.format(callback.from_user.id))
    if not file_id:
        await callback.answer("Фото больше не доступно. Отправь новое!", show_alert=True)
        return
    await callback.answer()
    if mode == "dating":
        await callback.message.answer("💕 Выбери стиль фото:", reply_markup=dating_style_keyboard())
    elif mode == "cv":
        await callback.message.answer("💼 Выбери стиль фото:", reply_markup=cv_style_keyboard())
    else:
        await _submit_analysis(callback, api_base_url, redis, mode, "")


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
    if mode == "cv":
        await callback.message.answer("💼 Выбери стиль фото:", reply_markup=cv_style_keyboard())
    else:
        await callback.message.answer("💕 Выбери стиль фото:", reply_markup=dating_style_keyboard())


@router.callback_query(F.data == "retry")
async def on_retry(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Retry last generation using stored last_gen context."""
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
        await callback.message.answer("📸 Выбери режим:", reply_markup=mode_selection_keyboard())
        return
    await _submit_analysis(callback, api_base_url, redis, mode, style)


async def _submit_analysis(callback: CallbackQuery, api_base_url: str, redis: Redis, mode: str, style: str):
    user_id = callback.from_user.id
    bot = callback.bot

    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return

    await callback.answer()
    status_msg = await callback.message.answer("⏳ Анализирую твоё фото... Это займёт 15-30 секунд.")

    await redis.set(LAST_GEN_KEY.format(user_id), f"{mode}:{style}", ex=86400)

    try:
        file = await bot.get_file(file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)
        image_data = file_bytes.read()

        form_data = {"mode": mode}
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

        elif resp.status_code == 402:
            from src.bot.keyboards import upgrade_keyboard
            await status_msg.edit_text(
                "🔒 Кредиты для генерации закончились!\nКупи пакет, чтобы продолжить:",
                reply_markup=upgrade_keyboard(),
            )
        elif resp.status_code == 429:
            await status_msg.edit_text(
                "⚠️ Дневной лимит исчерпан. Попробуй завтра или оформи Premium!",
                reply_markup=error_keyboard(),
            )
        else:
            detail = resp.json().get("detail", "Unknown error")
            await status_msg.edit_text(f"❌ Ошибка: {detail}", reply_markup=error_keyboard())

    except Exception:
        logger.exception("Failed to submit analysis for user %s", user_id)
        await status_msg.edit_text("❌ Произошла ошибка. Попробуй позже.", reply_markup=error_keyboard())


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
    wait_msg = await callback.message.answer("💳 Создаю платёж...")

    result = await create_payment(callback.from_user.id, pack_qty)
    if result is None:
        await wait_msg.edit_text(
            "❌ Не удалось создать платёж. Попробуйте позже.",
            reply_markup=error_keyboard(),
        )
        return

    payment_id, confirmation_url = result
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {pack.price_rub} ₽", url=confirmation_url)],
        [InlineKeyboardButton(text="💰 Проверить баланс", callback_data="balance")],
    ])
    await wait_msg.edit_text(
        f"🛒 *Пакет: {pack.quantity} генераций за {pack.price_rub} ₽*\n\n"
        f"Нажми кнопку ниже для оплаты.\n"
        f"После оплаты кредиты зачислятся автоматически!",
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
                f"💰 *Твой баланс*\n\n"
                f"Доступно генераций: *{credits}*\n\n"
            )
            if credits == 0:
                text += "Купи пакет, чтобы генерировать фото!"
                from src.bot.keyboards import upgrade_keyboard
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=upgrade_keyboard())
            else:
                text += "Отправь фото для генерации!"
                from src.bot.keyboards import back_keyboard
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            await callback.message.answer("❌ Не удалось получить баланс.", reply_markup=error_keyboard())
    except Exception:
        logger.exception("Failed to fetch balance for user %s", user_id)
        await callback.message.answer("❌ Ошибка. Попробуй позже.", reply_markup=error_keyboard())


@router.callback_query(F.data == "new_photo")
async def on_new_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Отправь мне новое фото!")


async def _poll_task(bot, api_base_url: str, user_id: int, task_id: str, chat_id: int, status_msg_id: int, redis: Redis):
    """Wait for task via Redis Pub/Sub, with HTTP polling fallback."""
    import asyncio
    from src.bot.handlers.results import deliver_result

    channel = f"ratemeai:task_done:{task_id}"
    notified = False

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            for _ in range(120):
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    notified = True
                    break
        finally:
            await pubsub.unsubscribe(channel)
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
                    await deliver_result(bot, chat_id, status_msg_id, data, user_id, redis)
                    return
                elif status == "failed":
                    error = data.get("error_message", "Неизвестная ошибка")
                    await bot.edit_message_text(
                        f"❌ Анализ не удался: {error}",
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        reply_markup=error_keyboard(),
                    )
                    return

            except Exception:
                logger.exception("Poll error for task %s", task_id)

            if notified:
                await asyncio.sleep(1)

        await bot.edit_message_text(
            "⏰ Анализ занимает слишком долго. Попробуй позже.",
            chat_id=chat_id,
            message_id=status_msg_id,
            reply_markup=error_keyboard(),
        )
