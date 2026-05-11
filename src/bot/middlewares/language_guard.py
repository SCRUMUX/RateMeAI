"""Language-based region guard for the Telegram bot.

The project runs **two independent bots** with strict regional separation:

* ``@RateMeAI_bot`` lives on the VPS (deployment_mode=edge, market=ru).
  It is the *only* bot that may persist Russian users' Telegram ID,
  username and first_name in its database (152-ФЗ).
* ``@AI_Look_Studio_bot`` lives on Railway (deployment_mode=primary,
  market=global). It serves everyone else.

A Telegram user with ``language_code in {ru, be, kk, uk, ky}`` who
accidentally writes to the Global bot would otherwise have their PII
written to the Global Postgres on Railway — that's exactly the
boundary we want to keep clean. Symmetrically, a non-RU user on the
RU bot would have their data live on a server hosted in Russia, which
is undesirable for them.

This middleware runs **before** :class:`src.bot.middleware.UserRegistrationMiddleware`,
so it can short-circuit the request before any DB write happens.
When the user is in the wrong region, the bot sends a one-line
reply with a deep-link to the correct peer bot and the handler chain
is aborted.

If ``settings.peer_bot_username`` is empty the guard logs a warning
and lets the message through — useful for dev / single-bot deploys.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.config import settings

logger = logging.getLogger(__name__)

RU_LANGUAGE_CODES: frozenset[str] = frozenset({"ru", "be", "kk", "uk", "ky"})

RU_BOT_USERNAMES: frozenset[str] = frozenset({"ratemeai_bot"})
GLOBAL_BOT_USERNAMES: frozenset[str] = frozenset({"ai_look_studio_bot"})


def _normalize_username(value: str) -> str:
    return value.lstrip("@").strip().lower()


def _current_bot_region() -> str | None:
    """Return "ru" | "global" | None based on TELEGRAM_BOT_USERNAME."""
    uname = _normalize_username(settings.telegram_bot_username or "")
    if not uname:
        return None
    if uname in RU_BOT_USERNAMES:
        return "ru"
    if uname in GLOBAL_BOT_USERNAMES:
        return "global"
    return None


def _is_ru_speaker(language_code: str | None) -> bool:
    if not language_code:
        return False
    return language_code.split("-", 1)[0].strip().lower() in RU_LANGUAGE_CODES


_RU_REJECTION_TEXT = (
    "Привет! Этот бот работает с пользователями вне РФ.\n\n"
    "Для русскоязычных пользователей у нас есть отдельный бот: "
    "https://t.me/{peer}\n\n"
    "Открой его и нажми /start — там всё на русском и оплата в рублях."
)

_GLOBAL_REJECTION_TEXT = (
    "Hi! This bot serves users in Russia only.\n\n"
    "For everyone else we have a separate bot: https://t.me/{peer}\n\n"
    "Open it and tap /start to begin."
)


class LanguageGuardMiddleware(BaseMiddleware):
    """Block cross-region traffic on the very first event, no DB writes.

    Decision matrix:

    * RU bot (``@RateMeAI_bot``)        : accept iff user is RU-speaking.
    * Global bot (``@AI_Look_Studio_bot``): accept iff user is NOT RU-speaking.
    * Unknown bot username              : log + pass-through (dev mode).
    * Missing ``language_code``         : pass-through. Telegram sets it
      from the client locale; ``None`` is rare and we don't want to
      reject silent users — instead the regular flow will handle them.
    """

    def __init__(self) -> None:
        self._region = _current_bot_region()
        self._peer = _normalize_username(settings.peer_bot_username or "")
        if self._region is None:
            logger.warning(
                "LanguageGuard: unknown TELEGRAM_BOT_USERNAME=%r — guard disabled. "
                "Whitelist: RU=%s GLOBAL=%s",
                settings.telegram_bot_username,
                sorted(RU_BOT_USERNAMES),
                sorted(GLOBAL_BOT_USERNAMES),
            )
        if not self._peer:
            logger.warning(
                "LanguageGuard: PEER_BOT_USERNAME is empty — cross-region "
                "redirects are disabled. Set PEER_BOT_USERNAME in env "
                "(see src/config.py:peer_bot_username) to enable."
            )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self._region is None or not self._peer:
            return await handler(event, data)

        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is None:
            return await handler(event, data)

        ru_speaker = _is_ru_speaker(user.language_code)
        accept = (self._region == "ru" and ru_speaker) or (
            self._region == "global" and not ru_speaker
        )

        if accept:
            return await handler(event, data)

        # Wrong region — reply with a deep-link to the peer bot and abort.
        # IMPORTANT: do this BEFORE any DB-touching middleware so we never
        # persist Telegram-side identifiers in the wrong region.
        text = (
            _RU_REJECTION_TEXT if self._region == "global" else _GLOBAL_REJECTION_TEXT
        ).format(peer=self._peer)

        try:
            if isinstance(event, Message):
                await event.answer(text, parse_mode=None, disable_web_page_preview=True)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
                if event.message is not None:
                    await event.message.answer(
                        text, parse_mode=None, disable_web_page_preview=True
                    )
        except Exception:
            logger.exception(
                "LanguageGuard: failed to deliver cross-region notice to user %s",
                user.id,
            )

        logger.info(
            "LanguageGuard: dropped %s on %s bot (telegram_id_hash=%s language_code=%s peer=%s)",
            type(event).__name__,
            self._region,
            hash(user.id) & 0xFFFF,
            user.language_code,
            self._peer,
        )
        return None
