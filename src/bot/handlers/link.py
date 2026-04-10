"""Bot /link command — generate or enter a cross-platform linking code."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import httpx
from redis.asyncio import Redis

from src.bot.middleware import get_bot_auth_headers

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("link"))
async def cmd_link(message: Message, api_base_url: str, redis: Redis):
    """Handle /link — generate code or claim an existing one.

    /link        → generate a code for the current user
    /link ABC123 → claim code and attach this telegram identity to code owner's account
    """
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    code = parts[1].strip().upper() if len(parts) > 1 else ""

    headers = await get_bot_auth_headers(redis, user_id)
    if not headers:
        await message.answer(
            "Сначала отправь любое сообщение, чтобы зарегистрироваться.",
        )
        return

    if code:
        await _claim_link_code(message, api_base_url, user_id, code, headers, redis)
    else:
        await _generate_link_code(message, api_base_url, headers)


async def _generate_link_code(message: Message, api_base_url: str, headers: dict[str, str]):
    """Call POST /auth/link-token to get a 6-character code."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/auth/link-token",
                headers=headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            code = data["code"]
            link_url = data.get("link_url", "")
            text = (
                f"\U0001f517 *Код привязки:* `{code}`\n\n"
                f"Действует 10 минут.\n\n"
                f"Откройте веб-приложение и введите этот код на странице привязки"
            )
            if link_url:
                text += f", или перейдите по ссылке:\n{link_url}"
            await message.answer(text, parse_mode="Markdown")
        else:
            await message.answer("\u274c Не удалось создать код привязки.")
    except Exception:
        logger.exception("Failed to generate link code for user %s", message.from_user.id)
        await message.answer("\u274c Ошибка. Попробуй позже.")


async def _claim_link_code(
    message: Message,
    api_base_url: str,
    user_id: int,
    code: str,
    headers: dict[str, str],
    redis: Redis,
):
    """Call POST /auth/claim-link to attach this telegram identity to the code owner."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/auth/claim-link",
                json={
                    "code": code,
                    "provider": "telegram",
                    "external_id": str(user_id),
                    "profile_data": {
                        "username": message.from_user.username,
                        "first_name": message.from_user.first_name,
                    },
                },
                headers=headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            new_token = data.get("session_token")
            if new_token:
                from src.bot.middleware import _BOT_SESSION_KEY, _BOT_SESSION_TTL
                await redis.set(
                    _BOT_SESSION_KEY.format(user_id),
                    new_token,
                    ex=_BOT_SESSION_TTL,
                )
            await message.answer(
                "\u2705 *Аккаунт привязан!*\n\n"
                "Теперь ваш аккаунт в боте и на сайте — это один аккаунт.",
                parse_mode="Markdown",
            )
        elif resp.status_code == 400:
            await message.answer("\u274c Код недействителен или истёк. Попросите новый код.")
        elif resp.status_code == 409:
            await message.answer(
                "\u274c Этот аккаунт Telegram уже привязан к другому пользователю."
            )
        else:
            detail = resp.json().get("detail", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
            await message.answer(f"\u274c Не удалось привязать аккаунт. {detail}")
    except Exception:
        logger.exception("Failed to claim link code for user %s", user_id)
        await message.answer("\u274c Ошибка. Попробуй позже.")
