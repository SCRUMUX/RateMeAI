"""Consent gate middleware.

Blocks any non-trivial interaction with the bot until the user has
granted all required consents (``data_processing``, ``ai_transfer``,
``age_confirmed_16``).  Whitelisted commands and callbacks are allowed
through so the user can still authenticate, view the privacy / help /
support screens, and revoke consents.

Cached state lives in Redis under ``bot_consent_ok:{tg_id}`` so the
backend is consulted at most once per session window.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import httpx
from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    Message,
    PreCheckoutQuery,
    TelegramObject,
)
from redis.asyncio import Redis

from src.bot.middleware import get_bot_auth_headers
from src.config import settings

logger = logging.getLogger(__name__)


CONSENT_OK_KEY = "bot_consent_ok:{}"
# Long-lived cache: as soon as the user has granted consent we trust
# the Redis flag for the rest of their session window.  Cleared on
# ``/privacy`` revoke.
_CONSENT_OK_TTL = max(settings.session_ttl_seconds - 3600, 3600)


# Commands that always pass — onboarding, info, consent management.
_BYPASS_COMMANDS: frozenset[str] = frozenset({
    "/start",
    "/privacy",
    "/help",
    "/support",
})

# Callback-data prefixes that must pass through without consent (the
# consent grant button itself, navigation, support deep-link).
_BYPASS_CALLBACK_PREFIXES: tuple[str, ...] = (
    "consent:",
    "link_cancel",
    "privacy:",
    "support:",
)


def _command_root(text: str | None) -> str | None:
    if not text:
        return None
    head = text.split(maxsplit=1)[0]
    if not head.startswith("/"):
        return None
    if "@" in head:
        head = head.split("@", 1)[0]
    return head.lower()


def _should_bypass(event: TelegramObject) -> bool:
    """Return True for events that must NOT be gated by consent."""
    if isinstance(event, PreCheckoutQuery):
        return True
    if isinstance(event, Message):
        if event.successful_payment is not None:
            return True
        cmd = _command_root(event.text or event.caption)
        if cmd in _BYPASS_COMMANDS:
            return True
        return False
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        for prefix in _BYPASS_CALLBACK_PREFIXES:
            if data == prefix or data.startswith(prefix):
                return True
        return False
    # Unknown update type — let it through; consent gate doesn't apply.
    return True


async def _fetch_consent_state(
    api_base_url: str,
    headers: dict[str, str],
) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/users/me/consents",
                headers=headers,
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        logger.warning("consent middleware: state fetch failed", exc_info=True)
    return None


async def mark_consent_ok(redis: Redis, telegram_id: int) -> None:
    """Set the consent-ok cache flag after a successful grant."""
    try:
        await redis.set(CONSENT_OK_KEY.format(telegram_id), "1", ex=_CONSENT_OK_TTL)
    except Exception:
        logger.debug("consent cache write failed for tg_id=%s", telegram_id, exc_info=True)


async def clear_consent_ok(redis: Redis, telegram_id: int) -> None:
    """Drop the consent-ok cache after revoke / version bump."""
    try:
        await redis.delete(CONSENT_OK_KEY.format(telegram_id))
    except Exception:
        logger.debug("consent cache drop failed for tg_id=%s", telegram_id, exc_info=True)


class ConsentMiddleware(BaseMiddleware):
    """Gate every event until required consents are recorded.

    Runs AFTER :class:`UserRegistrationMiddleware`, so a valid bot
    session token is already present in Redis for ``get_bot_auth_headers``.
    """

    def __init__(self, api_base_url: str, redis: Redis):
        self._api_base_url = api_base_url.rstrip("/")
        self._redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if _should_bypass(event):
            return await handler(event, data)

        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is None:
            return await handler(event, data)

        # Fast path: Redis cache says consents are in place.
        try:
            cached = await self._redis.get(CONSENT_OK_KEY.format(user.id))
        except Exception:
            cached = None
        if cached:
            return await handler(event, data)

        # Slow path: consult the backend.
        headers = await get_bot_auth_headers(self._redis, user.id)
        if not headers:
            # No session yet — middleware order should normally prevent
            # this (registration happens first), but if we're here, hand
            # control back so the user can hit /start without surprises.
            return await handler(event, data)

        state = await _fetch_consent_state(self._api_base_url, headers)
        if state is None:
            # Soft-fail: don't block real traffic on a transient API blip,
            # but DO surface the issue in logs.
            logger.warning(
                "Consent state unavailable for tg_id=%s; allowing through",
                user.id,
            )
            return await handler(event, data)

        missing = state.get("missing") or []
        if not missing:
            await mark_consent_ok(self._redis, user.id)
            return await handler(event, data)

        # Show the consent prompt and stop the chain.
        from src.bot.handlers.consent import send_consent_prompt

        try:
            await send_consent_prompt(event, missing)
        except Exception:
            logger.exception("Failed to send consent prompt for tg_id=%s", user.id)

        # Acknowledge callback queries so the spinner clears even though
        # we're refusing to run the actual handler.
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        return None
