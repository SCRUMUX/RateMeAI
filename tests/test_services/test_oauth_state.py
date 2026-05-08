"""Unit tests for ``src.services.oauth_state``.

The Redis layer is faked with an in-memory dict so we can run without a
live server. The tests focus on Stage 0 of the visa OAuth fix (1.57.0):
``return_path`` must round-trip through ``save_oauth_state`` /
``pop_oauth_state``.
"""

from __future__ import annotations

import pytest

from src.services.oauth_state import (
    pop_oauth_state,
    save_oauth_state,
)


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key, value, ex=None):  # noqa: D401 — Redis-compatible signature
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.mark.asyncio
async def test_return_path_round_trips(fake_redis):
    await save_oauth_state(
        fake_redis,
        "state-1",
        provider="google",
        device_id="dev-1",
        return_path="/visa/schengen",
    )
    payload = await pop_oauth_state(fake_redis, "state-1")
    assert payload is not None
    assert payload["return_path"] == "/visa/schengen"
    assert payload["provider"] == "google"
    assert payload["device_id"] == "dev-1"


@pytest.mark.asyncio
async def test_pop_consumes_state(fake_redis):
    await save_oauth_state(
        fake_redis,
        "state-2",
        provider="yandex",
        return_path="/visa/usa",
    )
    first = await pop_oauth_state(fake_redis, "state-2")
    second = await pop_oauth_state(fake_redis, "state-2")
    assert first is not None
    assert second is None  # state must be one-shot


@pytest.mark.asyncio
async def test_unknown_state_is_none(fake_redis):
    assert await pop_oauth_state(fake_redis, "missing") is None


@pytest.mark.asyncio
async def test_return_path_optional(fake_redis):
    """Saving without ``return_path`` keeps the field None — callers
    treat that as "redirect to /"."""
    await save_oauth_state(
        fake_redis,
        "state-3",
        provider="vk_id",
    )
    payload = await pop_oauth_state(fake_redis, "state-3")
    assert payload is not None
    assert payload["return_path"] is None
