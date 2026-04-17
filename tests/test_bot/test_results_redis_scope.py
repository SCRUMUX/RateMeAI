"""Regression test for Redis gen_image key scoping.

Баг: после geo-split рефактора writers (worker / edge-handler) начали скопить
ключ `ratemeai:gen_image:<task_id>` по market_id
(`ratemeai:gen_image:<market>:<task_id>`), но readers (бот и `/storage/*` роут)
читали ключ без scope. В результате бот не находил байты картинки в Redis,
падал на URL-фоллбек, а тот тоже не доставал файл — и пользователь получал
текст без фото.

Этот тест имитирует поведение writer'а (ключ со scope) и проверяет, что бот
действительно читает те же самые байты через `_fetch_gen_image_from_redis`.
"""
from __future__ import annotations

import base64

import pytest

from src.utils.redis_keys import gen_image_cache_key, legacy_gen_image_cache_key


class FakeAsyncRedis:
    """Небольшая async-замена Redis для теста: только get/set/delete."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def get(self, key: str):
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()


@pytest.fixture
def market_settings(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "market_id", "global")
    return settings


@pytest.mark.asyncio
async def test_bot_reader_picks_up_scoped_key_written_by_worker(
    fake_redis, market_settings,
):
    """Worker пишет ключ со scope — бот обязан его прочитать и расшифровать."""
    from src.bot.handlers.results import _fetch_gen_image_from_redis

    task_id = "11111111-1111-1111-1111-111111111111"
    payload = b"\xff\xd8\xff\xe0fake-jpg-bytes"
    b64_payload = base64.b64encode(payload).decode()

    scoped_key = gen_image_cache_key(task_id, market_settings.resolved_market_id)
    assert scoped_key == "ratemeai:gen_image:global:" + task_id
    await fake_redis.set(scoped_key, b64_payload)

    got = await _fetch_gen_image_from_redis(fake_redis, task_id)
    assert got == payload
    assert scoped_key not in fake_redis._store, "reader должен удалить ключ после чтения"


@pytest.mark.asyncio
async def test_bot_reader_falls_back_to_legacy_key(fake_redis, market_settings):
    """Для задач из эпохи до geo-split ключ без scope (legacy) всё ещё должен читаться."""
    from src.bot.handlers.results import _fetch_gen_image_from_redis

    task_id = "22222222-2222-2222-2222-222222222222"
    payload = b"legacy-bytes"
    b64_payload = base64.b64encode(payload).decode()

    legacy_key = legacy_gen_image_cache_key(task_id)
    await fake_redis.set(legacy_key, b64_payload)

    got = await _fetch_gen_image_from_redis(fake_redis, task_id)
    assert got == payload


@pytest.mark.asyncio
async def test_bot_reader_returns_none_when_no_key(fake_redis, market_settings):
    from src.bot.handlers.results import _fetch_gen_image_from_redis

    got = await _fetch_gen_image_from_redis(fake_redis, "deadbeef")
    assert got is None
