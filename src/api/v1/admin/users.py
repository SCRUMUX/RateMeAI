"""Session-admin Users tab — list users, inspect transactions/tasks,
adjust credits and book ledger refunds.

Mounted at ``/api/v1/admin/users`` and gated by
:func:`src.api.v1.admin.auth.require_admin`. The existing
``/api/v1/internal/admin/grant-credits`` (X-Internal-Key) endpoint
is intentionally untouched — that surface is consumed by the
GitHub Actions workflow and the admin bot, and breaking either
would be operationally painful.

Privacy invariants
------------------
None of the responses include ``Task.input_image_path`` or
``Task.share_card_path``. The ``tasks`` collection is selected
column-by-column to make this impossible to regress.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_redis
from src.api.v1.admin.auth import require_admin
from src.models.db import (
    CreditTransaction,
    Task,
    UsageLog,
    User,
    UserIdentity,
)
from src.services.admin_lookup import (
    collect_identity_emails,
    search_users_by_query,
)
from src.services.user_purge import purge_user

logger = logging.getLogger(__name__)

router = APIRouter()


MAX_AMOUNT = 100_000


# ---------------------------------------------------------------------------
# Response shapes (kept intentionally narrow)
# ---------------------------------------------------------------------------


def _identity_summary(identity: UserIdentity) -> dict[str, Any]:
    data = identity.profile_data or {}
    return {
        "provider": identity.provider,
        "external_id": identity.external_id,
        "email": data.get("email"),
        "username": data.get("username"),
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "created_at": (
            identity.created_at.isoformat() if identity.created_at else None
        ),
    }


def _user_row(
    user: User,
    *,
    identities: list[UserIdentity],
    total_generations: int,
    last_task_at: datetime | None,
    last_seen: datetime | None,
) -> dict[str, Any]:
    emails = collect_identity_emails(identities)
    providers = sorted({i.provider for i in identities if i.provider})
    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "is_premium": user.is_premium,
        "image_credits": user.image_credits,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "providers": providers,
        "emails": emails,
        "primary_email": emails[0] if emails else None,
        "total_generations": total_generations,
        "last_task_at": last_task_at.isoformat() if last_task_at else None,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "blocked_at": user.blocked_at.isoformat() if user.blocked_at else None,
        "blocked_reason": user.blocked_reason,
        "blocked_by": str(user.blocked_by) if user.blocked_by else None,
    }


# ---------------------------------------------------------------------------
# Aggregates per-user — cheap thanks to the index on (user_id, created_at)
# ---------------------------------------------------------------------------


async def _aggregate_for_users(
    db: AsyncSession, user_ids: list[UUID]
) -> tuple[
    dict[UUID, list[UserIdentity]],
    dict[UUID, int],
    dict[UUID, datetime | None],
    dict[UUID, datetime | None],
]:
    """Single round trip per aggregate type — never N+1.

    Returns ``(identities, total_generations, last_task_at, last_seen)``
    each keyed by ``user_id``. Missing keys default to empty/zero/None
    in the caller.
    """
    if not user_ids:
        return {}, {}, {}, {}

    identities_q = select(UserIdentity).where(UserIdentity.user_id.in_(user_ids))
    by_user_idents: dict[UUID, list[UserIdentity]] = {}
    for ident in (await db.execute(identities_q)).scalars().all():
        by_user_idents.setdefault(ident.user_id, []).append(ident)

    counts_q = (
        select(Task.user_id, func.count(Task.id), func.max(Task.created_at))
        .where(Task.user_id.in_(user_ids))
        .group_by(Task.user_id)
    )
    counts: dict[UUID, int] = {}
    last_task: dict[UUID, datetime | None] = {}
    for uid, cnt, ts in (await db.execute(counts_q)).all():
        counts[uid] = int(cnt or 0)
        last_task[uid] = ts

    seen_q = (
        select(UsageLog.user_id, func.max(UsageLog.usage_date))
        .where(UsageLog.user_id.in_(user_ids))
        .group_by(UsageLog.user_id)
    )
    last_seen: dict[UUID, datetime | None] = {}
    for uid, ts in (await db.execute(seen_q)).all():
        if ts is None:
            last_seen[uid] = None
        elif isinstance(ts, datetime):
            last_seen[uid] = ts
        else:
            # ``UsageLog.usage_date`` is a Date — promote to datetime
            # at midnight UTC so the JSON field is consistently
            # ISO-8601 with a timezone.
            last_seen[uid] = datetime(
                ts.year, ts.month, ts.day, tzinfo=timezone.utc
            )

    return by_user_idents, counts, last_task, last_seen


# ---------------------------------------------------------------------------
# GET /admin/users — paginated list with substring search
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_users(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Substring search across username / telegram_id /
    profile_data.email + recent-first ordering.

    Pagination is intentionally simple: bump ``limit`` if you
    need more rows. The Users tab is an ops surface, not a
    consumer-facing list, so we keep the implementation small.
    """
    users = await search_users_by_query(db, q=q, limit=limit)
    if not users:
        return {"items": [], "count": 0, "query": q, "limit": limit}

    user_ids = [u.id for u in users]
    idents, counts, last_task, last_seen = await _aggregate_for_users(
        db, user_ids
    )

    items = [
        _user_row(
            u,
            identities=idents.get(u.id, []),
            total_generations=counts.get(u.id, 0),
            last_task_at=last_task.get(u.id),
            last_seen=last_seen.get(u.id),
        )
        for u in users
    ]

    return {
        "items": items,
        "count": len(items),
        "query": q,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# GET /admin/users/{user_id} — full detail card
# ---------------------------------------------------------------------------


def _parse_user_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400, detail="user_id must be a UUID"
        ) from e


async def _load_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    uid = _parse_user_id(user_id)
    user = await _load_user_or_404(db, uid)

    idents, counts, last_task, last_seen = await _aggregate_for_users(
        db, [uid]
    )
    summary = _user_row(
        user,
        identities=idents.get(uid, []),
        total_generations=counts.get(uid, 0),
        last_task_at=last_task.get(uid),
        last_seen=last_seen.get(uid),
    )

    tx_q = (
        select(CreditTransaction)
        .where(CreditTransaction.user_id == uid)
        .order_by(CreditTransaction.created_at.desc())
        .limit(50)
    )
    transactions = [
        {
            "id": tx.id,
            "amount": tx.amount,
            "balance_after": tx.balance_after,
            "tx_type": tx.tx_type,
            "payment_id": tx.payment_id,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in (await db.execute(tx_q)).scalars().all()
    ]

    # Strict column allow-list — must NOT include input_image_path or
    # share_card_path. The Users tab is intentionally photo-blind.
    tasks_q = (
        select(
            Task.id,
            Task.mode,
            Task.status,
            Task.created_at,
            Task.completed_at,
            Task.error_message,
        )
        .where(Task.user_id == uid)
        .order_by(Task.created_at.desc())
        .limit(20)
    )
    tasks_rows = (await db.execute(tasks_q)).all()
    tasks = [
        {
            "id": str(tid),
            "mode": mode,
            "status": status,
            "created_at": ca.isoformat() if ca else None,
            "completed_at": cca.isoformat() if cca else None,
            "error_message": err,
        }
        for tid, mode, status, ca, cca, err in tasks_rows
    ]

    identities_payload = [
        _identity_summary(ident) for ident in idents.get(uid, [])
    ]

    return {
        "user": summary,
        "identities": identities_payload,
        "transactions": transactions,
        "tasks": tasks,
    }


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/credits  — adjust balance (+ or -)
# ---------------------------------------------------------------------------


class AdjustCreditsRequest(BaseModel):
    amount: int = Field(
        ...,
        description=(
            "Positive to grant, negative to debit. "
            "Must satisfy 0 < |amount| <= 100000."
        ),
    )
    reason: str = Field(..., min_length=3, max_length=255)


@router.post("/users/{user_id}/credits")
async def adjust_credits(
    user_id: str,
    payload: AdjustCreditsRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.amount == 0 or abs(payload.amount) > MAX_AMOUNT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"amount must be a non-zero integer in "
                f"[-{MAX_AMOUNT}, {MAX_AMOUNT}]"
            ),
        )

    uid = _parse_user_id(user_id)
    user = await _load_user_or_404(db, uid)

    before = int(user.image_credits or 0)
    after = before + payload.amount
    if after < 0:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "insufficient_credits",
                "message": (
                    f"Cannot debit {abs(payload.amount)} credits — "
                    f"current balance is {before}."
                ),
                "balance": before,
            },
        )

    user.image_credits = after
    tx_type = "admin_grant" if payload.amount > 0 else "admin_debit"
    tx = CreditTransaction(
        user_id=uid,
        amount=payload.amount,
        balance_after=after,
        tx_type=tx_type,
        payment_id=payload.reason[:255],
    )
    db.add(tx)

    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception(
            "admin_credits: failed to commit adjustment for user %s", uid
        )
        raise HTTPException(
            status_code=500, detail="Failed to record credit adjustment"
        )

    await db.refresh(user)
    await db.refresh(tx)

    logger.info(
        "admin_credits: admin=%s user=%s %+d credits (%d → %d) reason=%s",
        admin.id,
        uid,
        payload.amount,
        before,
        user.image_credits,
        payload.reason,
    )

    return {
        "status": "ok",
        "tx_type": tx_type,
        "before": before,
        "after": user.image_credits,
        "amount": payload.amount,
        "transaction_id": tx.id,
    }


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/refund  — ledger-only refund
# ---------------------------------------------------------------------------


class RefundRequest(BaseModel):
    credits: int = Field(..., gt=0, le=MAX_AMOUNT)
    payment_id: str | None = Field(default=None, max_length=255)
    note: str = Field(..., min_length=3, max_length=500)


@router.post("/users/{user_id}/refund")
async def refund_credits(
    user_id: str,
    payload: RefundRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    uid = _parse_user_id(user_id)
    user = await _load_user_or_404(db, uid)

    before = int(user.image_credits or 0)
    if payload.credits > before:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "insufficient_credits",
                "message": (
                    f"Cannot refund {payload.credits} credits — "
                    f"current balance is {before}."
                ),
                "balance": before,
            },
        )

    after = before - payload.credits
    user.image_credits = after

    audit_payload = (
        f"{payload.payment_id} | {payload.note}"
        if payload.payment_id
        else payload.note
    )[:255]

    tx = CreditTransaction(
        user_id=uid,
        amount=-payload.credits,
        balance_after=after,
        tx_type="admin_refund",
        payment_id=audit_payload,
    )
    db.add(tx)

    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception(
            "admin_refund: failed to commit refund for user %s", uid
        )
        raise HTTPException(
            status_code=500, detail="Failed to record refund"
        )

    await db.refresh(user)
    await db.refresh(tx)

    logger.info(
        "admin_refund: admin=%s user=%s -%d credits (%d → %d) note=%s",
        admin.id,
        uid,
        payload.credits,
        before,
        user.image_credits,
        payload.note,
    )

    return {
        "status": "ok",
        "tx_type": "admin_refund",
        "before": before,
        "after": user.image_credits,
        "credits": payload.credits,
        "transaction_id": tx.id,
    }


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/block  — soft-block account (in-app message)
# ---------------------------------------------------------------------------


class BlockRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: str,
    payload: BlockRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark a user as blocked. ``get_auth_user`` will refuse all
    subsequent requests with 403 ``account_blocked`` and the frontend
    will show a full-screen overlay.

    No external messaging here — by design, the user simply sees the
    in-app block screen the next time they hit the API. Existing
    sessions don't need to be revoked because the dependency check
    fails on every authenticated request.
    """
    uid = _parse_user_id(user_id)
    user = await _load_user_or_404(db, uid)

    if user.id == admin.id:
        raise HTTPException(
            status_code=400, detail="Cannot block your own admin account"
        )

    user.blocked_at = datetime.now(timezone.utc)
    user.blocked_reason = payload.reason.strip()
    user.blocked_by = admin.id

    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("admin_block: failed to commit for user %s", uid)
        raise HTTPException(status_code=500, detail="Failed to block user")

    await db.refresh(user)

    logger.info(
        "admin_block: admin=%s user=%s reason=%s",
        admin.id,
        uid,
        payload.reason,
    )

    return {
        "status": "ok",
        "blocked_at": user.blocked_at.isoformat() if user.blocked_at else None,
        "blocked_reason": user.blocked_reason,
        "blocked_by": str(user.blocked_by) if user.blocked_by else None,
    }


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/unblock  — clear block fields
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/unblock")
async def unblock_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    uid = _parse_user_id(user_id)
    user = await _load_user_or_404(db, uid)

    user.blocked_at = None
    user.blocked_reason = None
    user.blocked_by = None

    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("admin_unblock: failed to commit for user %s", uid)
        raise HTTPException(status_code=500, detail="Failed to unblock user")

    logger.info("admin_unblock: admin=%s user=%s", admin.id, uid)
    return {"status": "ok", "blocked_at": None}


# ---------------------------------------------------------------------------
# DELETE /admin/users/{user_id}  — full erasure via shared purge service
# ---------------------------------------------------------------------------


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Full erasure of a user's account by an admin (152-ФЗ ст. 14).

    Goes through the same ``purge_user`` service as the self-serve
    ``DELETE /users/me`` endpoint, but stamps the deletion log with
    ``source="admin"`` so the audit trail can distinguish the two.
    """
    uid = _parse_user_id(user_id)
    user = await _load_user_or_404(db, uid)

    if user.id == admin.id:
        raise HTTPException(
            status_code=400, detail="Cannot delete your own admin account"
        )

    result = await purge_user(
        user=user,
        db=db,
        redis=redis,
        source="admin",
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    logger.info("admin_delete: admin=%s user=%s", admin.id, uid)
    return result
