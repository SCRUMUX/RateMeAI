from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

PHOTO_KEY = "rateme:photo:{}"


class UserRegistrationMiddleware(BaseMiddleware):
    """Ensures user is registered in the API before handling any update."""

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
                    data["api_user"] = resp.json()
            except Exception:
                logger.exception("Failed to register user %s", user.id)

        data["api_base_url"] = self._api_base_url
        return await handler(event, data)
