"""Tests for session token management."""
from __future__ import annotations

import uuid

import pytest

from src.services.sessions import create_session, resolve_session, revoke_session


@pytest.fixture
def fake_redis(tmp_path):
    """In-memory dict-based fake Redis for unit tests."""
    class FakeRedis:
        def __init__(self):
            self._store = {}

        async def set(self, key, value, ex=None):
            self._store[key] = value

        async def get(self, key):
            return self._store.get(key)

        async def delete(self, key):
            self._store.pop(key, None)

    return FakeRedis()


@pytest.mark.asyncio
async def test_create_and_resolve(fake_redis):
    uid = uuid.uuid4()
    token = await create_session(fake_redis, uid)
    assert token
    resolved = await resolve_session(fake_redis, token)
    assert resolved == uid


@pytest.mark.asyncio
async def test_resolve_invalid(fake_redis):
    result = await resolve_session(fake_redis, "nonexistent_token")
    assert result is None


@pytest.mark.asyncio
async def test_revoke(fake_redis):
    uid = uuid.uuid4()
    token = await create_session(fake_redis, uid)
    await revoke_session(fake_redis, token)
    assert await resolve_session(fake_redis, token) is None
