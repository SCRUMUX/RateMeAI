from __future__ import annotations

import io
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
import httpx

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("mode:"))
async def on_mode_selected(callback: CallbackQuery, api_base_url: str):
    mode = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    bot = callback.bot

    photos = getattr(bot, "_user_photos", {})
    file_id = photos.get(user_id)

    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return

    await callback.answer()
    status_msg = await callback.message.answer("⏳ Анализирую твоё фото... Это займёт 10-20 секунд.")

    try:
        file = await bot.get_file(file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)
        image_data = file_bytes.read()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/analyze",
                files={"image": ("photo.jpg", image_data, "image/jpeg")},
                data={"mode": mode},
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

            # Start polling in background
            import asyncio
            asyncio.create_task(_poll_task(bot, api_base_url, user_id, task_id, callback.message.chat.id, status_msg.message_id))

        elif resp.status_code == 429:
            await status_msg.edit_text("⚠️ Дневной лимит исчерпан. Попробуй завтра или оформи Premium!")
        else:
            detail = resp.json().get("detail", "Unknown error")
            await status_msg.edit_text(f"❌ Ошибка: {detail}")

    except Exception:
        logger.exception("Failed to submit analysis for user %s", user_id)
        await status_msg.edit_text("❌ Произошла ошибка. Попробуй позже.")

    photos.pop(user_id, None)


@router.callback_query(F.data == "new_photo")
async def on_new_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Отправь мне новое фото!")


async def _poll_task(bot, api_base_url: str, user_id: int, task_id: str, chat_id: int, status_msg_id: int):
    """Poll API until task completes, then deliver result."""
    import asyncio
    from src.bot.handlers.results import deliver_result

    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(30):
            await asyncio.sleep(3)
            try:
                resp = await client.get(
                    f"{api_base_url}/api/v1/tasks/{task_id}",
                    headers={"X-Telegram-Id": str(user_id)},
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                status = data.get("status")

                if status == "completed":
                    await deliver_result(bot, chat_id, status_msg_id, data, user_id)
                    return
                elif status == "failed":
                    error = data.get("error_message", "Неизвестная ошибка")
                    await bot.edit_message_text(
                        f"❌ Анализ не удался: {error}",
                        chat_id=chat_id,
                        message_id=status_msg_id,
                    )
                    return

            except Exception:
                logger.exception("Poll error for task %s", task_id)

        await bot.edit_message_text(
            "⏰ Анализ занимает слишком долго. Попробуй позже.",
            chat_id=chat_id,
            message_id=status_msg_id,
        )
