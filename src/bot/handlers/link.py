"""Bot account-linking wizard — button-driven flow with /link shortcut."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import httpx
from redis.asyncio import Redis

from src.bot.keyboards import back_keyboard, link_waiting_keyboard, link_wizard_keyboard
from src.bot.middleware import get_bot_auth_headers

router = Router()
logger = logging.getLogger(__name__)

_LINK_WAITING_KEY = "ratemeai:link_waiting:{}"
_LINK_WAITING_TTL = 600  # 10 min — same as link-token TTL


# ---------------------------------------------------------------------------
# Custom filter: intercept plain text when user is in "waiting for code" state
# ---------------------------------------------------------------------------

class LinkCodeFilter(BaseFilter):
    """Match non-command text messages when the user has an active link_waiting flag."""

    async def __call__(self, message: Message, redis: Redis | None = None, **kwargs) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        if redis is None:
            return False
        try:
            flag = await redis.get(_LINK_WAITING_KEY.format(message.from_user.id))
            return flag is not None
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Callback: entry point — "Привязать аккаунт" button
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "link_account")
async def on_link_account(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "\U0001f517 *Привязка аккаунта*\n\n"
        "Привяжи аккаунт, чтобы использовать сервис\n"
        "и на сайте, и в боте \u2014 баланс и фото будут общими.\n\n"
        "Выбери свою ситуацию:",
        parse_mode="Markdown",
        reply_markup=link_wizard_keyboard(),
    )


# ---------------------------------------------------------------------------
# Path A: "У меня есть аккаунт на сайте" — user enters code from website
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "link_have_web")
async def on_link_have_web(callback: CallbackQuery, redis: Redis):
    await callback.answer()
    user_id = callback.from_user.id
    await redis.set(_LINK_WAITING_KEY.format(user_id), "1", ex=_LINK_WAITING_TTL)
    await callback.message.answer(
        "\U0001f310 *Привязка через сайт*\n\n"
        "1\ufe0f\u20e3 Зайди на сайт *ailookstudio.ru*\n"
        "2\ufe0f\u20e3 Нажми на баланс вверху \u2192 *Получить код привязки*\n"
        "3\ufe0f\u20e3 Скопируй 6-значный код\n"
        "4\ufe0f\u20e3 *Отправь код прямо сюда в чат* \u2935\ufe0f\n\n"
        "Жду код...",
        parse_mode="Markdown",
        reply_markup=link_waiting_keyboard(),
    )


# ---------------------------------------------------------------------------
# Path B: "Хочу войти на сайт через бот" — bot generates code
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "link_to_web")
async def on_link_to_web(callback: CallbackQuery, api_base_url: str, redis: Redis):
    await callback.answer()
    user_id = callback.from_user.id
    headers = await get_bot_auth_headers(redis, user_id)
    if not headers:
        await callback.message.answer(
            "\u274c Сначала отправь любое сообщение, чтобы зарегистрироваться.",
            reply_markup=back_keyboard(),
        )
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/auth/link-token",
                headers=headers,
            )
        if resp.status_code != 200:
            await callback.message.answer(
                "\u274c Не удалось создать код. Попробуй позже.",
                reply_markup=back_keyboard(),
            )
            return

        data = resp.json()
        code = data["code"]
        link_url = data.get("link_url", "")

        rows = []
        if link_url:
            rows.append([InlineKeyboardButton(
                text="\U0001f310 Открыть сайт",
                url=link_url,
            )])
        rows.append([InlineKeyboardButton(text="\u2b05 Назад", callback_data="link_cancel")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.answer(
            f"\U0001f4f2 *Привязка через бот*\n\n"
            f"Твой код привязки: `{code}`\n"
            f"Действует 10 минут.\n\n"
            f"1\ufe0f\u20e3 Нажми *Открыть сайт* ниже\n"
            f"2\ufe0f\u20e3 Код уже будет заполнен\n"
            f"3\ufe0f\u20e3 Выбери способ входа: Яндекс, ВК или телефон\n"
            f"4\ufe0f\u20e3 Готово \u2014 аккаунты объединены! \u2705",
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Failed to generate link code for user %s", user_id)
        await callback.message.answer(
            "\u274c Ошибка. Попробуй позже.",
            reply_markup=back_keyboard(),
        )


# ---------------------------------------------------------------------------
# Cancel — clear waiting flag, return to main menu
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "link_cancel")
async def on_link_cancel(callback: CallbackQuery, redis: Redis):
    await callback.answer()
    await redis.delete(_LINK_WAITING_KEY.format(callback.from_user.id))
    await callback.message.answer(
        "\U0001f4f8 Отправь мне фото для улучшения образа!",
        reply_markup=back_keyboard(),
    )


# ---------------------------------------------------------------------------
# Text handler: receive link code while in waiting state
# ---------------------------------------------------------------------------

@router.message(LinkCodeFilter())
async def on_link_code_text(message: Message, api_base_url: str, redis: Redis):
    user_id = message.from_user.id
    code = message.text.strip().upper()

    await redis.delete(_LINK_WAITING_KEY.format(user_id))

    headers = await get_bot_auth_headers(redis, user_id)
    if not headers:
        await message.answer(
            "\u274c Сначала отправь любое сообщение, чтобы зарегистрироваться.",
            reply_markup=back_keyboard(),
        )
        return

    await _claim_link_code(message, api_base_url, user_id, code, headers, redis)


# ---------------------------------------------------------------------------
# /link command — power-user shortcut (kept for backward compatibility)
# ---------------------------------------------------------------------------

@router.message(Command("link"))
async def cmd_link(message: Message, api_base_url: str, redis: Redis):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    code = parts[1].strip().upper() if len(parts) > 1 else ""

    await redis.delete(_LINK_WAITING_KEY.format(user_id))

    headers = await get_bot_auth_headers(redis, user_id)
    if not headers:
        await message.answer(
            "Сначала отправь любое сообщение, чтобы зарегистрироваться.",
        )
        return

    if code:
        await _claim_link_code(message, api_base_url, user_id, code, headers, redis)
    else:
        await message.answer(
            "\U0001f517 *Привязка аккаунта*\n\n"
            "Привяжи аккаунт, чтобы использовать сервис\n"
            "и на сайте, и в боте \u2014 баланс и фото будут общими.\n\n"
            "Выбери свою ситуацию:",
            parse_mode="Markdown",
            reply_markup=link_wizard_keyboard(),
        )


# ---------------------------------------------------------------------------
# Shared helper: claim a link code via API
# ---------------------------------------------------------------------------

async def _claim_link_code(
    message: Message,
    api_base_url: str,
    user_id: int,
    code: str,
    headers: dict[str, str],
    redis: Redis,
):
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
                from src.bot.middleware import _BOT_SESSION_KEY, _bot_session_ttl
                await redis.set(
                    _BOT_SESSION_KEY.format(user_id),
                    new_token,
                    ex=_bot_session_ttl(),
                )
            await message.answer(
                "\u2705 *Аккаунт привязан!*\n\n"
                "Теперь твой аккаунт в боте и на сайте \u2014 это один аккаунт.\n"
                "Баланс и история фото \u2014 общие.",
                parse_mode="Markdown",
                reply_markup=back_keyboard(),
            )
        elif resp.status_code == 400:
            await message.answer(
                "\u274c Код недействителен или истёк.\n\n"
                "Попроси новый код на сайте или нажми кнопку ниже.",
                reply_markup=link_wizard_keyboard(),
            )
        elif resp.status_code == 409:
            await message.answer(
                "\u274c Этот аккаунт Telegram уже привязан к другому пользователю.",
                reply_markup=back_keyboard(),
            )
        else:
            detail = ""
            if resp.headers.get("content-type", "").startswith("application/json"):
                detail = resp.json().get("detail", "")
            await message.answer(
                f"\u274c Не удалось привязать аккаунт. {detail}",
                reply_markup=back_keyboard(),
            )
    except Exception:
        logger.exception("Failed to claim link code for user %s", user_id)
        await message.answer(
            "\u274c Ошибка. Попробуй позже.",
            reply_markup=back_keyboard(),
        )
