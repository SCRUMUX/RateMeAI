"""Per-user style variant rotation with Redis-backed anti-repeat memory.

When the user clicks «Другой вариант» on a generation result, the bot
calls :func:`resolve_next_variant` to pick a :class:`StyleVariant` the
user has not seen yet for the given ``(mode, style)``. Once the pool of
unseen variants is exhausted, the memory is wiped and the full pool
becomes available again — so diversity keeps flowing indefinitely
while guaranteeing no back-to-back repeats.

Document-style generations (passport / visa / etc.) are intentionally
opted out: their scene must stay rigorously uniform and any
diversification would break compliance.
"""
from __future__ import annotations

import logging
import random
from typing import Iterable

from redis.asyncio import Redis

from src.prompts.style_spec import StyleSpec, StyleVariant

logger = logging.getLogger(__name__)

_SEEN_KEY_FMT = "ratemeai:seen_variants:{user_id}:{mode}:{style}"
_SEEN_TTL_SECONDS = 24 * 3600


def _key(user_id: int | str, mode: str, style: str) -> str:
    return _SEEN_KEY_FMT.format(
        user_id=user_id,
        mode=(mode or "").strip() or "_default",
        style=(style or "").strip() or "_default",
    )


async def _load_seen(redis: Redis, user_id: int | str, mode: str, style: str) -> set[str]:
    raw: Iterable = await redis.smembers(_key(user_id, mode, style))
    seen: set[str] = set()
    for item in raw or ():
        if isinstance(item, bytes):
            seen.add(item.decode("utf-8", errors="ignore"))
        elif isinstance(item, str):
            seen.add(item)
    return seen


async def resolve_next_variant(
    redis: Redis,
    spec: StyleSpec,
    user_id: int | str,
    mode: str,
    style: str,
) -> StyleVariant | None:
    """Pick the next un-seen :class:`StyleVariant` for (user, mode, style).

    Returns ``None`` when the style has no variants registered or is a
    document style. Otherwise uses a weighted random choice across the
    subset of variants the user has not consumed yet for this pool;
    when all variants have been seen the history is cleared and the
    full pool re-enters rotation.
    """
    variants = tuple(spec.variants or ())
    if not variants:
        return None

    try:
        seen = await _load_seen(redis, user_id, mode, style)
    except Exception as exc:  # noqa: BLE001
        # Resolver must never break generation — fall back to a random
        # choice when Redis is unavailable.
        logger.warning("variant resolver: redis read failed: %s", exc)
        seen = set()

    pool = [v for v in variants if v.id not in seen]
    if not pool:
        # Exhausted: reset memory and use the full pool again.
        try:
            await redis.delete(_key(user_id, mode, style))
        except Exception as exc:  # noqa: BLE001
            logger.warning("variant resolver: redis reset failed: %s", exc)
        pool = list(variants)

    weights = [max(float(v.weight), 0.0001) for v in pool]
    chosen = random.choices(pool, weights=weights, k=1)[0]

    try:
        key = _key(user_id, mode, style)
        await redis.sadd(key, chosen.id)
        await redis.expire(key, _SEEN_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("variant resolver: redis write failed: %s", exc)

    return chosen


async def clear_history(
    redis: Redis, user_id: int | str, mode: str, style: str,
) -> None:
    """Drop the seen-variants history for a single (user, mode, style)."""
    try:
        await redis.delete(_key(user_id, mode, style))
    except Exception as exc:  # noqa: BLE001
        logger.warning("variant resolver: redis clear failed: %s", exc)


__all__ = ["resolve_next_variant", "clear_history"]
