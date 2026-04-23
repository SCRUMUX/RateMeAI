"""User consent storage and enforcement.

Implements a split consent model: users must independently opt in to
- ``data_processing`` — base processing of personal data (face photos),
- ``ai_transfer`` — cross-border transfer to external AI providers
  (OpenRouter / Reve / Replicate).

Both are mandatory for any task creation; missing consents produce
HTTP 451 ``Unavailable For Legal Reasons``. The audit trail lives in the
``user_consents`` DB table; "current" state is cached in Redis for 1h.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import Task, UserConsent
from src.services.task_contract import get_market_id
from src.utils.redis_keys import (
    CONSENT_CACHE_TTL,
    consent_cache_key,
    gen_image_cache_keys,
    preanalysis_cache_keys,
    task_input_cache_keys,
)

logger = logging.getLogger(__name__)

CONSENT_DATA_PROCESSING = "data_processing"
CONSENT_AI_TRANSFER = "ai_transfer"
CONSENT_AGE_CONFIRMED_16 = "age_confirmed_16"

REQUIRED_CONSENT_KINDS: tuple[str, ...] = (
    CONSENT_DATA_PROCESSING,
    CONSENT_AI_TRANSFER,
    CONSENT_AGE_CONFIRMED_16,
)

CURRENT_CONSENT_VERSION = "1"


@dataclass(frozen=True)
class ActiveConsent:
    kind: str
    version: str
    granted_at: datetime
    source: str


def hash_marker(value: str | None) -> str | None:
    """SHA256 of a short marker (IP / user-agent) for audit without storing raw PII."""
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


async def _load_from_db(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, ActiveConsent]:
    result = await db.execute(
        select(UserConsent)
        .where(UserConsent.user_id == user_id, UserConsent.revoked_at.is_(None))
        .order_by(UserConsent.granted_at.desc())
    )
    active: dict[str, ActiveConsent] = {}
    for row in result.scalars().all():
        if row.kind in active:
            continue
        active[row.kind] = ActiveConsent(
            kind=row.kind,
            version=row.version,
            granted_at=row.granted_at,
            source=row.source,
        )
    return active


def _serialize_active(active: dict[str, ActiveConsent]) -> str:
    payload = {
        kind: {
            "version": item.version,
            "granted_at": item.granted_at.isoformat(),
            "source": item.source,
        }
        for kind, item in active.items()
    }
    return json.dumps(payload)


def _deserialize_active(raw: str) -> dict[str, ActiveConsent]:
    data = json.loads(raw)
    out: dict[str, ActiveConsent] = {}
    for kind, item in data.items():
        try:
            granted_at = datetime.fromisoformat(item["granted_at"])
        except (KeyError, ValueError):
            continue
        out[kind] = ActiveConsent(
            kind=kind,
            version=str(item.get("version", CURRENT_CONSENT_VERSION)),
            granted_at=granted_at,
            source=str(item.get("source", "unknown")),
        )
    return out


async def get_active_consents(
    db: AsyncSession,
    redis: Redis | None,
    user_id: uuid.UUID,
) -> dict[str, ActiveConsent]:
    """Return current consent state keyed by kind. Redis-cached for 1h."""
    if redis is not None:
        try:
            cached = await redis.get(consent_cache_key(str(user_id)))
            if cached:
                return _deserialize_active(cached)
        except Exception:
            logger.debug("consent cache read failed", exc_info=True)

    active = await _load_from_db(db, user_id)

    if redis is not None:
        try:
            await redis.set(
                consent_cache_key(str(user_id)),
                _serialize_active(active),
                ex=CONSENT_CACHE_TTL,
            )
        except Exception:
            logger.debug("consent cache write failed", exc_info=True)

    return active


async def invalidate_consent_cache(redis: Redis | None, user_id: uuid.UUID) -> None:
    if redis is None:
        return
    try:
        await redis.delete(consent_cache_key(str(user_id)))
    except Exception:
        logger.debug("consent cache invalidate failed", exc_info=True)


async def purge_user_pipeline_caches(
    db: AsyncSession,
    redis: Redis | None,
    user_id: uuid.UUID,
) -> int:
    """Drop every Redis key tied to the user's in-flight or cached tasks.

    Used on ``revoke_consent`` so that, immediately after the user pulls
    their AI-transfer consent, we cannot accidentally re-serve a cached
    generation or send a cached task_input to a provider. The physical
    deletion of already-stored generated files is still the job of
    ``privacy_gc_cron`` / ``DELETE /users/me``; this function only
    evicts short-lived pipeline caches (task_input, gen_image,
    preanalysis). Returns the number of Redis keys attempted for
    deletion.
    """
    if redis is None:
        return 0

    from src.config import (
        settings as _settings,
    )  # local import to avoid cycle at module load

    result = await db.execute(
        select(Task.id, Task.context).where(Task.user_id == user_id)
    )
    keys: list[str] = []
    for task_id, context in result.all():
        market_id = get_market_id(context, fallback=_settings.resolved_market_id)
        tid = str(task_id)
        keys.extend(task_input_cache_keys(tid, market_id))
        keys.extend(gen_image_cache_keys(tid, market_id))
        keys.extend(preanalysis_cache_keys(tid, market_id))

    keys.append(consent_cache_key(str(user_id)))

    if not keys:
        return 0

    try:
        await redis.delete(*keys)
    except Exception:
        logger.debug("pipeline cache purge failed", exc_info=True)
        return 0
    return len(keys)


async def grant_consent(
    db: AsyncSession,
    redis: Redis | None,
    user_id: uuid.UUID,
    kinds: list[str],
    *,
    version: str = CURRENT_CONSENT_VERSION,
    source: str = "web",
    ip_hash: str | None = None,
    user_agent_hash: str | None = None,
) -> dict[str, ActiveConsent]:
    """Record consent(s). Idempotent: re-granting an already active consent is a no-op."""
    existing = await _load_from_db(db, user_id)
    now = datetime.now(timezone.utc)
    added = False
    for kind in kinds:
        if kind in existing:
            continue
        db.add(
            UserConsent(
                user_id=user_id,
                kind=kind,
                version=version,
                source=source,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                granted_at=now,
            )
        )
        added = True
    if added:
        await db.commit()
        await invalidate_consent_cache(redis, user_id)
    return await get_active_consents(db, redis, user_id)


async def revoke_consent(
    db: AsyncSession,
    redis: Redis | None,
    user_id: uuid.UUID,
    kinds: list[str],
) -> dict[str, ActiveConsent]:
    """Mark active consents as revoked. Does not delete the audit row."""
    now = datetime.now(timezone.utc)
    changed = False
    for kind in kinds:
        result = await db.execute(
            select(UserConsent)
            .where(
                UserConsent.user_id == user_id,
                UserConsent.kind == kind,
                UserConsent.revoked_at.is_(None),
            )
            .order_by(UserConsent.granted_at.desc())
        )
        rows = result.scalars().all()
        for row in rows:
            row.revoked_at = now
            changed = True
    if changed:
        await db.commit()
        # Full cache purge — a revoke must take effect *immediately*, so in
        # addition to the consent-state cache we also evict every pipeline
        # artefact that could still be served from Redis (P1.4 privacy
        # audit). Physical deletion of storage files is handled
        # separately by privacy_gc_cron / DELETE /users/me.
        purged = await purge_user_pipeline_caches(db, redis, user_id)
        logger.info(
            "consent.revoked.cache_purge",
            extra={"user_id": str(user_id), "kinds": kinds, "purged_keys": purged},
        )
    return await get_active_consents(db, redis, user_id)


def missing_required(active: dict[str, ActiveConsent]) -> list[str]:
    """Return kinds that are missing OR stale relative to ``CURRENT_CONSENT_VERSION``.

    A consent is considered *missing* when either:

    - no active (non-revoked) row exists for that kind, OR
    - the latest active row was granted against an *older* policy version.

    The second branch implements re-consent on policy bumps: whenever the
    privacy-policy text changes materially we increment
    ``CURRENT_CONSENT_VERSION`` and every user is forced through the
    consent flow again (HTTP 451 via ``require_consents``).
    """
    missing: list[str] = []
    for kind in REQUIRED_CONSENT_KINDS:
        entry = active.get(kind)
        if entry is None:
            missing.append(kind)
            continue
        if str(entry.version) != str(CURRENT_CONSENT_VERSION):
            missing.append(kind)
    return missing


def snapshot_for_task(active: dict[str, ActiveConsent]) -> dict[str, dict[str, str]]:
    """Compact snapshot of active consents to store in Task.context."""
    return {
        kind: {
            "version": item.version,
            "granted_at": item.granted_at.isoformat(),
            "source": item.source,
        }
        for kind, item in active.items()
    }
