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

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_auth_user, get_db, get_redis
from src.models.db import (
    CreditTransaction,
    Task,
    User,
    UserConsent,
    UserIdentity,
    UserPerceptionRecord,
)
from src.services.user_purge import purge_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/users/me")
async def delete_my_account(
    request: Request,
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """GDPR Art. 17 / 152-ФЗ ст. 14 — right to erasure (self-serve)."""
    return await purge_user(
        user=user,
        db=db,
        redis=redis,
        source="api",
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


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
        (
            await db.execute(
                select(Task).where(Task.user_id == user_id).order_by(Task.created_at)
            )
        )
        .scalars()
        .all()
    )
    consents_rows = (
        (
            await db.execute(
                select(UserConsent)
                .where(UserConsent.user_id == user_id)
                .order_by(UserConsent.granted_at)
            )
        )
        .scalars()
        .all()
    )
    identities_rows = (
        (await db.execute(select(UserIdentity).where(UserIdentity.user_id == user_id)))
        .scalars()
        .all()
    )
    perception_rows = (
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
    credits_rows = (
        (
            await db.execute(
                select(CreditTransaction)
                .where(CreditTransaction.user_id == user_id)
                .order_by(CreditTransaction.created_at)
            )
        )
        .scalars()
        .all()
    )

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
