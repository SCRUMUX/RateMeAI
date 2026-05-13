"""Internal endpoints exposed to the Telegram bot (and the RU edge).

All routes here are protected by the ``X-Internal-Key`` header — the
same secret already used by ``/api/v1/internal/*``.  They are never
exposed publicly; the bot calls them from the same Railway project
and the RU edge calls them from the VPS over HTTPS.

Endpoints
---------

* ``POST /api/v1/internal/bot/stars/grant`` — idempotently credit a
  user after a successful Telegram Stars payment.  Called by the bot
  ``successful_payment`` handler.

* ``GET /api/v1/internal/bot/users/{tg_id}/profile`` — read-only
  lookup of a Telegram-linked user (introduced in 1.62.0 for the
  cross-region link-token flow on the RU edge).
"""

from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.models.db import User, UserIdentity
from src.services.payments.stars import record_stars_purchase

logger = logging.getLogger(__name__)
router = APIRouter()


async def _verify_internal_key(x_internal_key: str = Header(...)) -> str:
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="Internal API not configured")
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    return x_internal_key


class StarsGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_id: int = Field(..., ge=1)
    pack_qty: int = Field(..., ge=1, le=1000)
    telegram_payment_charge_id: str = Field(..., min_length=1, max_length=200)


class StarsGrantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    image_credits: int | None = None


async def _resolve_user_by_telegram_id(
    db: AsyncSession, telegram_id: int
) -> User | None:
    # 1.62.0 — tg users live in ``users.telegram_id`` (legacy) AND in
    # ``user_identities`` (modern multi-provider model).  Check both so
    # callers don't have to care which schema rev a given account was
    # created on.
    direct = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = direct.scalar_one_or_none()
    if user is not None:
        return user

    via_identity = await db.execute(
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(
            UserIdentity.provider == "telegram",
            UserIdentity.external_id == str(telegram_id),
        )
    )
    return via_identity.scalar_one_or_none()


@router.post(
    "/stars/grant",
    response_model=StarsGrantResponse,
    include_in_schema=False,
)
async def stars_grant(
    payload: StarsGrantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(_verify_internal_key),
) -> StarsGrantResponse:
    """Idempotently credit a user after Telegram Stars ``successful_payment``.

    Idempotency: ``telegram_payment_charge_id`` is stored in
    ``credit_transactions.payment_id`` with a ``stars:`` prefix.  The
    same charge_id replayed returns ``{"status": "duplicate"}``.
    """
    user = await _resolve_user_by_telegram_id(db, payload.telegram_id)
    if user is None:
        logger.error(
            "Stars grant: telegram_id=%s not found in users / user_identities",
            payload.telegram_id,
        )
        raise HTTPException(status_code=404, detail="user_not_found")

    redis = getattr(request.app.state, "redis", None)
    result = await record_stars_purchase(
        db,
        user_id=user.id,
        pack_qty=payload.pack_qty,
        charge_id=payload.telegram_payment_charge_id,
        redis=redis,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail", "error"))
    return StarsGrantResponse(
        status=result.get("status", "ok"),
        image_credits=result.get("image_credits"),
    )


class BotUserProfileResponse(BaseModel):
    """Subset of the bot-side user that the RU edge needs to link accounts.

    Intentionally minimal — no email, no chat history, no payment
    log.  The RU edge only uses ``image_credits`` to merge the bot
    balance into a web account.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    image_credits: int
    username: str | None = None
    language_code: str | None = None


@router.get(
    "/users/{telegram_id}/profile",
    response_model=BotUserProfileResponse,
    include_in_schema=False,
)
async def bot_user_profile(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(_verify_internal_key),
) -> BotUserProfileResponse:
    """Read-only profile of a Telegram-linked user (cross-region link)."""
    user = await _resolve_user_by_telegram_id(db, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return BotUserProfileResponse(
        user_id=str(user.id),
        image_credits=int(user.image_credits or 0),
        username=getattr(user, "username", None),
        # language_code is not persisted on the bot side as of 1.62.0;
        # the field is kept in the schema so RU edge clients can rely
        # on a stable shape when we start storing it.
        language_code=None,
    )


__all__ = ["router"]


# Defensive: silence unused import warning for _uuid when type hints get tree-shaken
_ = _uuid
