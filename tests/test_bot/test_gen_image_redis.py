"""Bot delivery helpers."""

from __future__ import annotations

import base64

import pytest
from unittest.mock import AsyncMock

from src.bot.handlers.results import _fetch_gen_image_from_redis


@pytest.mark.asyncio
async def test_fetch_gen_image_from_redis_does_not_delete_key():
    """TTL + consumers must co-exist; early delete broke /storage/ + URL fallback."""
    redis = AsyncMock()
    payload = base64.b64encode(b"\xff\xd8" + b"\x00" * 200 + b"\xff\xd9").decode()
    redis.get = AsyncMock(return_value=payload)

    data = await _fetch_gen_image_from_redis(
        redis, "550e8400-e29b-41d4-a716-446655440000"
    )

    assert data is not None
    assert len(data) > 100
    redis.delete.assert_not_called()
