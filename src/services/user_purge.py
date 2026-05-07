"""User-purge service: shared erasure logic for self-serve and admin paths.

GDPR Art. 17 / 152-ФЗ ст. 14 — right to erasure. Two callers go through this
service:

- ``DELETE /api/v1/users/me`` (``users_data.delete_my_account``) — the user
  themselves, ``source="api"``.
- ``DELETE /api/v1/admin/users/{id}`` — admin acting on behalf of the
  platform, ``source="admin"``.

Both should remove the SAME artefacts in the SAME order so the deletion log
is consistent regardless of who pressed the button. Order:

1. All storage artefacts (generated/<user>/<task>.jpg, share-cards, any
   lingering input_image_path that survived the immediate cleanup).
2. All user-scoped Redis keys (task_input, gen_image, preanalysis,
   consent cache).
3. The ``users`` row — ORM relationships cascade to tasks, consents,
   identities, usage_logs, credit_transactions, perception_records.
4. A PII-free audit row in ``deletion_log`` (only hashed markers).

The function is intentionally idempotent at the storage/Redis layer:
``_safe_*`` helpers swallow individual failures so a missing artefact
doesn't block the database delete (otherwise the user is stuck "half-deleted"
forever).
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import (
    DeletionLog,
    Task,
    User,
    UserConsent,
    UserIdentity,
    UserPerceptionRecord,
)
from src.providers.factory import get_storage
from src.services.consent import hash_marker
from src.services.task_contract import get_market_id
from src.utils.redis_keys import (
    consent_cache_key,
    gen_image_cache_keys,
    preanalysis_cache_keys,
    task_input_cache_keys,
)

logger = logging.getLogger(__name__)


def _hash_user_id(user_id: uuid.UUID) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()


async def _safe_storage_delete(storage, key: str | None) -> bool:
    if not key:
        return False
    try:
        await storage.delete(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.warning("user-purge: storage.delete(%s) failed", key, exc_info=True)
        return False


async def _safe_redis_delete(redis: Redis | None, keys: list[str]) -> None:
    if redis is None or not keys:
        return
    try:
        await redis.delete(*keys)
    except Exception:
        logger.debug("user-purge: redis delete failed", exc_info=True)


async def purge_user(
    *,
    user: User,
    db: AsyncSession,
    redis: Redis | None,
    source: str,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, int | bool | dict]:
    """Erase all artefacts for ``user`` and write a ``deletion_log`` row.

    Args:
        user: the user being deleted (already loaded from the same session).
        db: async session — committed before returning.
        redis: optional Redis instance for cache eviction.
        source: ``"api"`` (self-serve) or ``"admin"`` (admin panel) — written
            verbatim to ``deletion_log.source``.
        client_ip: caller's IP, hashed before being stored.
        user_agent: caller's UA, hashed before being stored.

    Returns:
        Counters of removed artefacts, suitable for direct JSON response.
    """
    user_id = user.id
    user_id_str = str(user_id)
    storage = get_storage()

    tasks_result = await db.execute(select(Task).where(Task.user_id == user_id))
    tasks = tasks_result.scalars().all()

    generated_deleted = 0
    share_cards_deleted = 0
    redis_keys_to_purge: list[str] = []

    for t in tasks:
        task_id_str = str(t.id)
        market_id = get_market_id(t.context, fallback=settings.resolved_market_id)

        if await _safe_storage_delete(
            storage, f"generated/{user_id_str}/{task_id_str}.jpg"
        ):
            generated_deleted += 1
        if t.share_card_path and await _safe_storage_delete(storage, t.share_card_path):
            share_cards_deleted += 1
        if t.input_image_path:
            await _safe_storage_delete(storage, t.input_image_path)

        redis_keys_to_purge.extend(task_input_cache_keys(task_id_str, market_id))
        redis_keys_to_purge.extend(gen_image_cache_keys(task_id_str, market_id))
        redis_keys_to_purge.extend(preanalysis_cache_keys(task_id_str, market_id))

    redis_keys_to_purge.append(consent_cache_key(user_id_str))
    await _safe_redis_delete(redis, redis_keys_to_purge)

    consents_count = (
        (await db.execute(select(UserConsent).where(UserConsent.user_id == user_id)))
        .scalars()
        .all()
    )
    identities_count = (
        (await db.execute(select(UserIdentity).where(UserIdentity.user_id == user_id)))
        .scalars()
        .all()
    )
    perception_count = (
        (
            await db.execute(
                select(UserPerceptionRecord).where(
                    UserPerceptionRecord.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )

    tasks_deleted = len(tasks)
    consents_deleted = len(consents_count)
    identities_deleted = len(identities_count)
    perception_deleted = len(perception_count)

    await db.delete(user)
    await db.flush()

    audit = DeletionLog(
        user_id_hash=_hash_user_id(user_id),
        source=source,
        ip_hash=hash_marker(client_ip),
        user_agent_hash=hash_marker(user_agent),
        tasks_deleted=tasks_deleted,
        generated_files_deleted=generated_deleted,
        share_cards_deleted=share_cards_deleted,
        consents_deleted=consents_deleted,
        perception_records_deleted=perception_deleted,
        identities_deleted=identities_deleted,
    )
    db.add(audit)
    await db.commit()

    logger.info(
        "user.deleted",
        extra={
            "user_id_hash": audit.user_id_hash,
            "source": source,
            "tasks": tasks_deleted,
            "generated": generated_deleted,
            "share_cards": share_cards_deleted,
            "consents": consents_deleted,
            "identities": identities_deleted,
            "perception": perception_deleted,
        },
    )

    return {
        "deleted": True,
        "artefacts": {
            "tasks": tasks_deleted,
            "generated_files": generated_deleted,
            "share_cards": share_cards_deleted,
            "consents": consents_deleted,
            "identities": identities_deleted,
            "perception_records": perception_deleted,
        },
    }
