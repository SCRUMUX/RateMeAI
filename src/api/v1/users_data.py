"""Data-subject endpoints: GDPR Art. 17 (erasure) and Art. 20 (portability).

- ``DELETE /api/v1/users/me`` — physically deletes all artefacts associated
  with the authenticated user and records a PII-free audit row in the
  ``deletion_log`` table (see alembic 010).
- ``GET  /api/v1/users/me/export`` — returns a JSON dump of everything the
  platform stores about the user (tasks, consents, credit transactions,
  perception records, identities).

Both endpoints intentionally sit in their own router and require a regular
auth session — no header-based B2B bypass.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_auth_user, get_db, get_redis
from src.models.db import (
    CreditTransaction,
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
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


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
        logger.warning("user-delete: storage.delete(%s) failed", key, exc_info=True)
        return False


async def _safe_redis_delete(redis: Redis | None, keys: list[str]) -> None:
    if redis is None or not keys:
        return
    try:
        await redis.delete(*keys)
    except Exception:
        logger.debug("user-delete: redis delete failed", exc_info=True)


@router.delete("/users/me")
async def delete_my_account(
    request: Request,
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """GDPR Art. 17 / 152-ФЗ ст. 14 — right to erasure.

    Removes, in order:
      1) All storage artefacts (generated/<user>/<task>.jpg, share-cards,
         any lingering input_image_path).
      2) All user-scoped Redis keys (task_input, gen_image, preanalysis,
         consent cache).
      3) The ``users`` row itself — relationships cascade via ORM, which
         triggers automatic deletion of tasks, consents, identities,
         usage_logs, credit_transactions, perception_records.
      4) An audit row in ``deletion_log`` with only hashed markers
         (user_id_hash, ip_hash, ua_hash) — no PII.
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

        if await _safe_storage_delete(storage, f"generated/{user_id_str}/{task_id_str}.jpg"):
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
        await db.execute(select(UserConsent).where(UserConsent.user_id == user_id))
    ).scalars().all()
    identities_count = (
        await db.execute(select(UserIdentity).where(UserIdentity.user_id == user_id))
    ).scalars().all()
    perception_count = (
        await db.execute(select(UserPerceptionRecord).where(UserPerceptionRecord.user_id == user_id))
    ).scalars().all()

    tasks_deleted = len(tasks)
    consents_deleted = len(consents_count)
    identities_deleted = len(identities_count)
    perception_deleted = len(perception_count)

    await db.delete(user)
    await db.flush()

    client_ip = request.client.host if request.client else None
    audit = DeletionLog(
        user_id_hash=_hash_user_id(user_id),
        source="api",
        ip_hash=hash_marker(client_ip),
        user_agent_hash=hash_marker(request.headers.get("user-agent")),
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


def _serialize_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


@router.get("/users/me/export")
async def export_my_data(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """GDPR Art. 20 — data portability.

    Streams a JSON document with everything the platform stores about the
    authenticated user. Intentionally excludes raw image bytes (which are
    not stored anyway — only URLs inside ``task.result`` persist).
    """
    user_id = user.id

    tasks_rows = (
        await db.execute(select(Task).where(Task.user_id == user_id).order_by(Task.created_at))
    ).scalars().all()
    consents_rows = (
        await db.execute(
            select(UserConsent).where(UserConsent.user_id == user_id).order_by(UserConsent.granted_at)
        )
    ).scalars().all()
    identities_rows = (
        await db.execute(select(UserIdentity).where(UserIdentity.user_id == user_id))
    ).scalars().all()
    perception_rows = (
        await db.execute(
            select(UserPerceptionRecord).where(UserPerceptionRecord.user_id == user_id)
        )
    ).scalars().all()
    credits_rows = (
        await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at)
        )
    ).scalars().all()

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": str(user.id),
            "username": user.username,
            "first_name": user.first_name,
            "is_premium": user.is_premium,
            "image_credits": user.image_credits,
            "created_at": _serialize_dt(user.created_at),
        },
        "tasks": [
            {
                "id": str(t.id),
                "mode": t.mode,
                "status": t.status,
                "context": t.context,
                "result": t.result,
                "error_message": t.error_message,
                "created_at": _serialize_dt(t.created_at),
                "updated_at": _serialize_dt(t.updated_at),
                "completed_at": _serialize_dt(t.completed_at),
            }
            for t in tasks_rows
        ],
        "consents": [
            {
                "kind": c.kind,
                "version": c.version,
                "source": c.source,
                "granted_at": _serialize_dt(c.granted_at),
                "revoked_at": _serialize_dt(c.revoked_at),
            }
            for c in consents_rows
        ],
        "identities": [
            {
                "provider": i.provider,
                "external_id": i.external_id,
                "profile_data": i.profile_data,
                "created_at": _serialize_dt(i.created_at),
            }
            for i in identities_rows
        ],
        "perception_records": [
            {
                "mode": p.mode,
                "style": p.style,
                "warmth": p.warmth,
                "presence": p.presence,
                "appeal": p.appeal,
                "authenticity": p.authenticity,
                "created_at": _serialize_dt(p.created_at),
                "updated_at": _serialize_dt(p.updated_at),
            }
            for p in perception_rows
        ],
        "credit_transactions": [
            {
                "amount": c.amount,
                "balance_after": c.balance_after,
                "tx_type": c.tx_type,
                "payment_id": c.payment_id,
                "created_at": _serialize_dt(c.created_at),
            }
            for c in credits_rows
        ],
    }

    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"ailookstudio-export-{user.id}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
