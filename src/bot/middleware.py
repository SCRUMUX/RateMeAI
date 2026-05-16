from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

PHOTO_KEY = "rateme:photo:{}"
_BOT_SESSION_KEY = "bot_session:{}"


def _bot_session_ttl() -> int:
    from src.config import settings

    return max(settings.session_ttl_seconds - 3600, 3600)


# P2.3: when the cached session token still has at least this much
# time left we treat it as fresh — anything below triggers an async
# refresh that does NOT block the current handler (previously we
# blocked for 200-400ms on every event whose token was within 1h of
# expiry, which felt sluggish on chatty conversations).
_MIN_REMAINING_TTL = 1800


async def get_bot_bearer_token(redis: Redis, telegram_id: int) -> str | None:
    """Retrieve stored Bearer token for a Telegram user."""
    raw = await redis.get(_BOT_SESSION_KEY.format(telegram_id))
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


async def get_bot_auth_headers(redis: Redis, telegram_id: int) -> dict[str, str]:
    """Return Authorization header dict for API calls from the bot."""
    token = await get_bot_bearer_token(redis, telegram_id)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


class UserRegistrationMiddleware(BaseMiddleware):
    """Ensures user is registered and has a fresh Bearer session for API calls."""

    def __init__(self, api_base_url: str, redis: Redis):
        self._api_base_url = api_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=10.0)
        self._redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["redis"] = self._redis

        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user:
            key = _BOT_SESSION_KEY.format(user.id)
            ttl = await self._redis.ttl(key)

            if ttl <= 0:
                # No token at all — must block, the very next handler
                # will need authenticated headers.
                await self._refresh_session(user, key)
            elif ttl < _MIN_REMAINING_TTL:
                # Token still valid; refresh in the background so the
                # current handler doesn't wait on the API round-trip.
                asyncio.create_task(self._refresh_session(user, key))

        data["api_base_url"] = self._api_base_url
        return await handler(event, data)

    async def _refresh_session(self, user, key: str) -> None:
        """Hit /auth/telegram, store the resulting session token."""
        try:
            resp = await self._client.post(
                f"{self._api_base_url}/api/v1/auth/telegram",
                json={
                    "telegram_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                },
            )
            if resp.status_code == 200:
                token = resp.json().get("session_token")
                if token:
                    await self._redis.set(key, token, ex=_bot_session_ttl())
        except Exception:
            logger.exception("Failed to register/refresh user %s", user.id)

    async def close(self) -> None:
        await self._client.aclose()
