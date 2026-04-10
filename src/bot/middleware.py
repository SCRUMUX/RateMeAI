from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

PHOTO_KEY = "rateme:photo:{}"
_BOT_SESSION_KEY = "bot_session:{}"
_BOT_SESSION_TTL = 86400 * 7  # 7 days


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
    """Ensures user is registered and has a Bearer session for API calls."""

    def __init__(self, api_base_url: str, redis: Redis):
        self._api_base_url = api_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=10.0)
        self._registered: set[int] = set()
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

        if user and user.id not in self._registered:
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
                    self._registered.add(user.id)
                    resp_data = resp.json()
                    data["api_user"] = resp_data

                    token = resp_data.get("session_token")
                    if token:
                        await self._redis.set(
                            _BOT_SESSION_KEY.format(user.id),
                            token,
                            ex=_BOT_SESSION_TTL,
                        )
            except Exception:
                logger.exception("Failed to register user %s", user.id)

        data["api_base_url"] = self._api_base_url
        return await handler(event, data)

    async def close(self) -> None:
        await self._client.aclose()
