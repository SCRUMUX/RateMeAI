"""Platform-agnostic session management backed by Redis."""
from __future__ import annotations

import secrets
import uuid
import logging

from redis.asyncio import Redis

from src.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "ratemeai:session:"


def _make_token() -> str:
    return secrets.token_urlsafe(48)


async def create_session(redis: Redis, user_id: uuid.UUID) -> str:
    token = _make_token()
    key = f"{_PREFIX}{token}"
    await redis.set(key, str(user_id), ex=settings.session_ttl_seconds)
    return token


async def resolve_session(redis: Redis, token: str) -> uuid.UUID | None:
    key = f"{_PREFIX}{token}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        val = raw.decode() if isinstance(raw, bytes) else raw
        return uuid.UUID(val)
    except ValueError:
        logger.warning("Corrupt session value for token ending ...%s", token[-8:])
        return None


async def revoke_session(redis: Redis, token: str) -> None:
    await redis.delete(f"{_PREFIX}{token}")
