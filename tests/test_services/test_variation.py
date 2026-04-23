"""Tests for StyleVariant rotation with Redis-backed anti-repeat memory."""

from __future__ import annotations

import pytest

from src.prompts.style_spec import StyleSpec, StyleVariant
from src.services.variation import (
    clear_history,
    resolve_next_variant,
)


class _FakeRedis:
    """Minimal in-memory Redis implementing the commands the service uses."""

    def __init__(self) -> None:
        self._sets: dict[str, set[str]] = {}

    async def smembers(self, key: str) -> set[bytes]:
        return {m.encode() for m in self._sets.get(key, set())}

    async def sadd(self, key: str, *members: str) -> int:
        bucket = self._sets.setdefault(key, set())
        added = 0
        for m in members:
            if m not in bucket:
                bucket.add(m)
                added += 1
        return added

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self._sets.pop(key, None) is not None:
                removed += 1
        return removed

    async def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002
        return key in self._sets


def _make_spec(
    variant_ids: list[str], mode: str = "dating", key: str = "yoga_outdoor"
) -> StyleSpec:
    variants = tuple(
        StyleVariant(id=vid, scene=f"scene-{vid}", lighting="warm light")
        for vid in variant_ids
    )
    return StyleSpec(
        key=key,
        mode=mode,
        background="placeholder",
        clothing_male="placeholder",
        clothing_female="placeholder",
        lighting="warm",
        expression="gentle",
        variants=variants,
    )


@pytest.mark.asyncio
async def test_resolve_next_variant_returns_none_without_variants():
    redis = _FakeRedis()
    spec = _make_spec([])
    result = await resolve_next_variant(redis, spec, 1, "dating", "yoga_outdoor")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_next_variant_uses_full_pool_without_repeats():
    redis = _FakeRedis()
    spec = _make_spec(["a", "b", "c", "d"])

    picks = []
    for _ in range(4):
        v = await resolve_next_variant(redis, spec, 42, "dating", "yoga_outdoor")
        assert v is not None
        picks.append(v.id)

    assert set(picks) == {"a", "b", "c", "d"}
    assert len(set(picks)) == 4


@pytest.mark.asyncio
async def test_resolve_next_variant_resets_after_full_pool_consumed():
    redis = _FakeRedis()
    spec = _make_spec(["a", "b"])

    first_pair = []
    for _ in range(2):
        v = await resolve_next_variant(redis, spec, 7, "dating", "yoga_outdoor")
        assert v is not None
        first_pair.append(v.id)
    assert set(first_pair) == {"a", "b"}

    third = await resolve_next_variant(redis, spec, 7, "dating", "yoga_outdoor")
    assert third is not None
    assert third.id in {"a", "b"}


@pytest.mark.asyncio
async def test_clear_history_allows_same_variant_to_appear_again():
    redis = _FakeRedis()
    spec = _make_spec(["a"])
    v1 = await resolve_next_variant(redis, spec, 99, "dating", "yoga_outdoor")
    assert v1.id == "a"
    await clear_history(redis, 99, "dating", "yoga_outdoor")
    v2 = await resolve_next_variant(redis, spec, 99, "dating", "yoga_outdoor")
    assert v2.id == "a"


@pytest.mark.asyncio
async def test_resolver_tolerates_redis_failures():
    class _BrokenRedis(_FakeRedis):
        async def smembers(self, key):  # noqa: ARG002
            raise RuntimeError("redis down")

    redis = _BrokenRedis()
    spec = _make_spec(["a", "b", "c", "d"])
    v = await resolve_next_variant(redis, spec, 1, "dating", "yoga_outdoor")
    assert v is not None
    assert v.id in {"a", "b", "c", "d"}
