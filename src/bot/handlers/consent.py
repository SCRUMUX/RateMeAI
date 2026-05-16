"""Telegram consent flow (privacy/compliance).

Whenever a user attempts an action that requires consent (anything
except the whitelisted onboarding / info / support commands), the
``ConsentMiddleware`` calls :func:`send_consent_prompt` to show a
single-button consent prompt.  The button posts all three required
consents at once so the user is not forced through three separate
clicks before the bot becomes useful.

The legacy per-kind callbacks (``consent:grant:{kind}``) are kept so
old messages in chat history continue to work — but they now share the
same backend call and Redis cache as the grant-all path.
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
    TelegramObject,
)
from redis.asyncio import Redis

from src.bot.middleware import get_bot_auth_headers
from src.bot.middlewares.consent import (
    clear_consent_ok,
    mark_consent_ok,
)
from src.config import settings

logger = logging.getLogger(__name__)

router = Router()

_ALL_KINDS: tuple[str, ...] = ("data_processing", "ai_transfer", "age_confirmed_16")

CONSENT_REQUIRED_MESSAGE = (
    "\U0001f512 *Прежде чем начать, подтверди три согласия:*\n\n"
    "1\ufe0f\u20e3 *Обработка персональных данных* — я анализирую лицо и сохраняю "
    "скоры. Оригинал фото не хранится.\n\n"
    "2\ufe0f\u20e3 *Передача во внешние AI-сервисы* — для генерации я отправляю "
    "фото в OpenRouter / Reve (зарубежные провайдеры).\n\n"
    "3\ufe0f\u20e3 *Возраст 16+* — сервис не обслуживает несовершеннолетних "
    "младше 16 лет.\n\n"
    "Все согласия обязательны. Отозвать можно в любой момент через /privacy."
)

_PRIVACY_URL_FALLBACK = "https://ailookstudio.ru/privacy"


def _resolve_privacy_url(language_code: str | None = None) -> str:
    """Build the privacy-policy URL from the bot landing host.

    Per-language since 1.62.0 — RU-family locales get the
    ``ailookstudio.ru`` policy, everyone else the global one.  Falls
    back to the historical RU URL when both per-language URLs are
    empty (e.g. local dev).
    """
    base = settings.resolve_landing_url(language_code)
    if not base:
        return _PRIVACY_URL_FALLBACK
    return f"{base}/privacy"


def _consent_keyboard_one_click(language_code: str | None = None) -> InlineKeyboardMarkup:
    """Single-button consent keyboard used by the middleware gate."""
    privacy_url = _resolve_privacy_url(language_code)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 Согласен и продолжаю",
                    callback_data="consent:grant_all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4dc Политика конфиденциальности",
                    url=privacy_url,
                )
            ],
        ]
    )


def _consent_keyboard(
    missing: list[str],
    privacy_url: str | None = None,
    language_code: str | None = None,
) -> InlineKeyboardMarkup:
    """Legacy per-kind keyboard — retained for backwards compatibility
    with messages already in the user's chat history."""
    if privacy_url is None:
        privacy_url = _resolve_privacy_url(language_code)
    buttons: list[list[InlineKeyboardButton]] = []
    if "data_processing" in missing:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="\u2705 Согласен на обработку ПДн",
                    callback_data="consent:grant:data_processing",
                )
            ]
        )
    if "ai_transfer" in missing:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="\u2705 Согласен на передачу во внешние AI",
                    callback_data="consent:grant:ai_transfer",
                )
            ]
        )
    if "age_confirmed_16" in missing:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="\u2705 Мне 16 лет или больше",
                    callback_data="consent:grant:age_confirmed_16",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="\U0001f4dc Политика конфиденциальности", url=privacy_url
            )
        ]
    )
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
    kinds: list[str],
) -> dict | None:
    try:
        resp = await client.post(
            f"{api_base_url}/api/v1/users/me/consents",
            headers=headers,
            json={"kinds": kinds, "source": "telegram"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        logger.warning("consent grant POST failed", exc_info=True)
    return None


async def send_consent_prompt(event: TelegramObject, missing: list[str]) -> None:
    """Send the one-click consent prompt for the given event.

    Used by :class:`ConsentMiddleware` whenever a non-whitelisted event
    needs consent.  Works for both ``Message`` and ``CallbackQuery``.
    """
    if isinstance(event, Message):
        user = event.from_user
        lang = getattr(user, "language_code", None) if user else None
        await event.answer(
            CONSENT_REQUIRED_MESSAGE,
            reply_markup=_consent_keyboard_one_click(language_code=lang),
            parse_mode="Markdown",
        )
        return
    if isinstance(event, CallbackQuery):
        user = event.from_user
        lang = getattr(user, "language_code", None) if user else None
        if event.message:
            await event.message.answer(
                CONSENT_REQUIRED_MESSAGE,
                reply_markup=_consent_keyboard_one_click(language_code=lang),
                parse_mode="Markdown",
            )
        return


async def ensure_consents(
    message: Message,
    redis: Redis,
    api_base_url: str,
) -> bool:
    """Legacy helper kept for backwards compatibility.

    Since the consent gate moved into :class:`ConsentMiddleware`, this
    function is no longer the primary enforcement point — but we keep
    it as a safety net for any code path that still wants an explicit
    pre-check (e.g. /start showing the prompt on first contact).
    Returns ``True`` when consents are already in place.
    """
    user = message.from_user
    if user is None:
        return True

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
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
        await mark_consent_ok(redis, user.id)
        return True

    await send_consent_prompt(message, missing)
    return False


@router.callback_query(F.data == "consent:grant_all")
async def on_consent_grant_all(
    callback: CallbackQuery,
    redis: Redis,
    api_base_url: str,
):
    """One-click grant for every required consent kind."""
    user = callback.from_user
    if user is None:
        await callback.answer()
        return

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
        await callback.answer(
            "Нужна авторизация. Нажми /start.",
            show_alert=True,
        )
        return

    async with httpx.AsyncClient() as client:
        state = await _post_consent_grant(
            client, api_base_url, headers, list(_ALL_KINDS)
        )

    if not state:
        await callback.answer(
            "Не удалось сохранить согласие. Попробуй ещё раз.",
            show_alert=True,
        )
        return

    missing = state.get("missing") or []
    if missing:
        # Backend rejected one or more kinds — keep the prompt up.
        await callback.answer(
            "Не все согласия удалось сохранить. Попробуй ещё раз.",
            show_alert=True,
        )
        return

    await mark_consent_ok(redis, user.id)

    try:
        await callback.message.edit_text(
            "\u2705 Согласия получены. Можешь присылать фото — я подберу образ.",
            parse_mode=None,
        )
    except Exception:
        # Old message may be too old to edit — send a fresh one.
        await callback.message.answer(
            "\u2705 Согласия получены. Можешь присылать фото — я подберу образ.",
            parse_mode=None,
        )
    await callback.answer("Готово!")


@router.callback_query(F.data.startswith("consent:grant:"))
async def on_consent_grant_legacy(
    callback: CallbackQuery,
    redis: Redis,
    api_base_url: str,
):
    """Legacy per-kind grant button — preserved for old chat history."""
    user = callback.from_user
    if user is None:
        await callback.answer()
        return

    kind = callback.data.split(":")[-1] if callback.data else ""
    if kind not in _ALL_KINDS:
        await callback.answer("Неизвестный тип согласия.", show_alert=True)
        return

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
        await callback.answer(
            "Нужна авторизация. Нажми /start.",
            show_alert=True,
        )
        return

    async with httpx.AsyncClient() as client:
        state = await _post_consent_grant(client, api_base_url, headers, [kind])

    if not state:
        await callback.answer(
            "Не удалось сохранить согласие. Попробуй ещё раз.",
            show_alert=True,
        )
        return

    missing = state.get("missing") or []
    if missing:
        lang = getattr(user, "language_code", None) if user else None
        # P1.3: refresh both the text and the keyboard so the user sees
        # how many consents are left, not just an updated button row.
        granted_count = len(_ALL_KINDS) - len(missing)
        new_text = (
            f"\U0001f512 *Согласия получено: {granted_count} из {len(_ALL_KINDS)}*\n\n"
            "Подтверди оставшиеся пункты, чтобы продолжить."
        )
        try:
            await callback.message.edit_text(
                new_text,
                reply_markup=_consent_keyboard(missing, language_code=lang),
                parse_mode="Markdown",
            )
        except Exception:
            await callback.message.edit_reply_markup(
                reply_markup=_consent_keyboard(missing, language_code=lang)
            )
        await callback.answer(
            "Согласие сохранено. Подтверди оставшиеся, чтобы продолжить.",
        )
        return

    await mark_consent_ok(redis, user.id)

    await callback.message.edit_text(
        "\u2705 Согласия получены. Можешь присылать фото — я сразу начну анализ.",
        parse_mode=None,
    )
    await callback.answer("Готово!")


@router.callback_query(F.data == "consent:revoke_all")
async def on_consent_revoke_all(
    callback: CallbackQuery,
    redis: Redis,
    api_base_url: str,
):
    """Revoke every required consent.  Triggered from /privacy."""
    user = callback.from_user
    if user is None:
        await callback.answer()
        return

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
        await callback.answer("Нужна авторизация. Нажми /start.", show_alert=True)
        return

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/users/me/consents/revoke",
                headers=headers,
                json={"kinds": list(_ALL_KINDS)},
            )
        ok = resp.status_code == 200
    except Exception:
        logger.warning("consent revoke failed", exc_info=True)
        ok = False

    if not ok:
        await callback.answer(
            "Не удалось отозвать. Попробуй ещё раз.", show_alert=True
        )
        return

    await clear_consent_ok(redis, user.id)
    lang = getattr(user, "language_code", None) if user else None

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 Дать согласие снова",
                    callback_data="consent:grant_all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4dc Политика конфиденциальности",
                    url=_resolve_privacy_url(lang),
                )
            ],
        ]
    )
    await callback.message.edit_text(
        "\U0001f6ab *Согласия отозваны.*\n\n"
        "Бот больше не сможет обрабатывать фото, пока ты не дашь согласие снова.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    await callback.answer("Согласия отозваны.")
