"""Info commands: /help, /support, /privacy.

Surfaced through ``set_my_commands`` so they appear in the Telegram menu.
``/privacy`` shows the current consent state and offers a revoke
button; ``/support`` shows a deep-link to the support chat;
``/help`` shows a short cheat-sheet plus links to policy and support.
"""

from __future__ import annotations

import logging

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from redis.asyncio import Redis

from src.bot.middleware import get_bot_auth_headers
from src.config import settings

logger = logging.getLogger(__name__)

router = Router()


SUPPORT_URL = "https://t.me/AI_Look_Studio"


def _privacy_url(language_code: str | None = None) -> str:
    base = settings.resolve_landing_url(language_code)
    if not base:
        return "https://ailookstudio.ru/privacy"
    return f"{base}/privacy"


def _support_button(text: str = "\u2709\ufe0f Поддержка") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=SUPPORT_URL)


HELP_TEXT = (
    "\U0001f4d6 *Что я умею*\n\n"
    "1. Отправь фото — выберу лучший образ для дейтинга, карьеры или соцсетей.\n"
    "2. Каждый новый стиль расходует 1 образ из баланса.\n"
    "3. Telegram Stars пополняют баланс мгновенно — оплата идёт прямо в чате.\n\n"
    "*Команды:*\n"
    "/start — главное меню\n"
    "/balance — баланс кредитов\n"
    "/link — привязать аккаунт на сайте\n"
    "/privacy — согласия и политика\n"
    "/support — связаться с поддержкой\n"
)


@router.message(Command("help"))
async def cmd_help(message: Message):
    lang = (
        getattr(message.from_user, "language_code", None)
        if message.from_user
        else None
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [_support_button()],
            [
                InlineKeyboardButton(
                    text="\U0001f4dc Политика конфиденциальности",
                    url=_privacy_url(lang),
                )
            ],
        ]
    )
    await message.answer(HELP_TEXT, parse_mode="Markdown", reply_markup=kb)


@router.message(Command("support"))
async def cmd_support(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[_support_button("\U0001f4ac Написать в поддержку")]]
    )
    await message.answer(
        "\U0001f4ac *Поддержка*\n\n"
        "Опиши проблему в чате @AI_Look_Studio — отвечаем в течение суток.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, api_base_url: str, redis: Redis):
    """Show consent state and offer a revoke button."""
    user = message.from_user
    if user is None:
        return

    lang = getattr(user, "language_code", None)
    privacy_url = _privacy_url(lang)

    headers = await get_bot_auth_headers(redis, user.id)
    if not headers:
        await message.answer(
            "Нужна авторизация. Нажми /start и попробуй снова.",
            parse_mode=None,
        )
        return

    state: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/users/me/consents", headers=headers
            )
        if resp.status_code == 200:
            state = resp.json()
    except Exception:
        logger.warning("privacy: fetch consents failed", exc_info=True)

    if state is None:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="\U0001f4dc Политика конфиденциальности",
                        url=privacy_url,
                    )
                ]
            ]
        )
        await message.answer(
            "Не удалось получить состояние согласий. Попробуй позже.",
            parse_mode=None,
            reply_markup=kb,
        )
        return

    missing = state.get("missing") or []
    granted = state.get("granted") or {}
    required = state.get("required") or []

    lines = ["\U0001f512 *Состояние согласий*", ""]
    label_map = {
        "data_processing": "Обработка персональных данных",
        "ai_transfer": "Передача во внешние AI-сервисы",
        "age_confirmed_16": "Подтверждение возраста 16+",
    }
    for kind in required:
        label = label_map.get(kind, kind)
        if kind in granted:
            lines.append(f"\u2705 {label}")
        else:
            lines.append(f"\u274c {label}")
    lines.append("")
    lines.append(
        "Полная политика и регламент обработки данных доступны по ссылке ниже."
    )

    rows: list[list[InlineKeyboardButton]] = []
    if missing:
        rows.append(
            [
                InlineKeyboardButton(
                    text="\u2705 Дать согласие",
                    callback_data="consent:grant_all",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f6ab Отозвать все согласия",
                    callback_data="consent:revoke_all",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="\U0001f4dc Политика конфиденциальности",
                url=privacy_url,
            )
        ]
    )
    rows.append([_support_button()])
    await message.answer(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
