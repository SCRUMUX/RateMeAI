"""Telegram consent flow (privacy/compliance).

On first photo upload (or whenever the backend still reports missing
consents) the bot shows an inline keyboard with two grant buttons and a
link to the privacy policy. Both consents are required before any photo
is forwarded to the analysis pipeline.
"""
from __future__ import annotations

import logging

import httpx
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from redis.asyncio import Redis

from src.bot.middleware import get_bot_auth_headers

logger = logging.getLogger(__name__)

router = Router()

CONSENT_REQUIRED_MESSAGE = (
    "\U0001f512 Прежде чем я смогу обработать фото, нужны три согласия:\n\n"
    "1\ufe0f\u20e3 *Обработка персональных данных* — я анализирую лицо и сохраняю "
    "скоры. Оригинал фото не хранится.\n\n"
    "2\ufe0f\u20e3 *Передача во внешние AI-сервисы* — для генерации я отправляю "
    "фото в OpenRouter / Reve (зарубежные провайдеры).\n\n"
    "3\ufe0f\u20e3 *Подтверждение возраста 16+* — сервис не обслуживает "
    "несовершеннолетних младше 16 лет.\n\n"
    "Все согласия обязательны. Отозвать можно в любой момент через /privacy."
)

_PRIVACY_URL_FALLBACK = "https://ailookstudio.ru/privacy"


def _consent_keyboard(
    missing: list[str],
    privacy_url: str = _PRIVACY_URL_FALLBACK,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if "data_processing" in missing:
        buttons.append([
            InlineKeyboardButton(
                text="\u2705 Согласен на обработку ПДн",
                callback_data="consent:grant:data_processing",
            )
        ])
    if "ai_transfer" in missing:
        buttons.append([
            InlineKeyboardButton(
                text="\u2705 Согласен на передачу во внешние AI",
                callback_data="consent:grant:ai_transfer",
            )
        ])
    if "age_confirmed_16" in missing:
        buttons.append([
            InlineKeyboardButton(
                text="\u2705 Мне 16 лет или больше",
                callback_data="consent:grant:age_confirmed_16",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="\U0001f4dc Политика конфиденциальности", url=privacy_url)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _fetch_consent_state(
    client: httpx.AsyncClient,
    api_base_url: str,
    headers: dict[str, str],
) -> dict | None:
    try:
        resp = await client.get(
            f"{api_base_url}/api/v1/users/me/consents",
            headers=headers,
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        logger.warning("consent fetch failed", exc_info=True)
    return None


async def _post_consent_grant(
    client: httpx.AsyncClient,
    api_base_url: str,
    headers: dict[str, str],
    kind: str,
) -> dict | None:
    try:
        resp = await client.post(
            f"{api_base_url}/api/v1/users/me/consents",
            headers=headers,
            json={"kinds": [kind], "source": "telegram"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        logger.warning("consent grant POST failed", exc_info=True)
    return None


async def ensure_consents(
    message: Message,
    redis: Redis,
    api_base_url: str,
) -> bool:
    """Block the photo flow until both required consents are granted.

    Returns True when consents are already in place (or have just been
    granted via this prompt); False when the bot asked the user for consent
    and must wait for a callback-query before continuing.
    """
    user = message.from_user
    if user is None:
        return True

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
        # Without a session we cannot verify consent — fail closed.
        await message.answer(
            "Нужна авторизация. Нажми /start и попробуй снова.",
            parse_mode=None,
        )
        return False

    async with httpx.AsyncClient() as client:
        state = await _fetch_consent_state(client, api_base_url, headers)

    if not state:
        await message.answer(
            "Не удалось проверить согласия. Попробуй /start ещё раз.",
            parse_mode=None,
        )
        return False

    missing = state.get("missing") or []
    if not missing:
        return True

    await message.answer(
        CONSENT_REQUIRED_MESSAGE,
        reply_markup=_consent_keyboard(missing),
        parse_mode="Markdown",
    )
    return False


@router.callback_query(F.data.startswith("consent:grant:"))
async def on_consent_grant(
    callback: CallbackQuery,
    redis: Redis,
    api_base_url: str,
):
    user = callback.from_user
    if user is None:
        await callback.answer()
        return

    kind = callback.data.split(":")[-1] if callback.data else ""
    if kind not in ("data_processing", "ai_transfer", "age_confirmed_16"):
        await callback.answer("Неизвестный тип согласия.", show_alert=True)
        return

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
        await callback.answer(
            "Нужна авторизация. Нажми /start.", show_alert=True,
        )
        return

    async with httpx.AsyncClient() as client:
        state = await _post_consent_grant(client, api_base_url, headers, kind)

    if not state:
        await callback.answer(
            "Не удалось сохранить согласие. Попробуй ещё раз.",
            show_alert=True,
        )
        return

    missing = state.get("missing") or []
    if missing:
        await callback.message.edit_reply_markup(
            reply_markup=_consent_keyboard(missing)
        )
        await callback.answer(
            "Согласие сохранено. Подтверди оставшиеся, чтобы продолжить.",
        )
        return

    await callback.message.edit_text(
        "\u2705 Согласия получены. Можешь присылать фото — я сразу начну анализ.",
        parse_mode=None,
    )
    await callback.answer("Готово!")
