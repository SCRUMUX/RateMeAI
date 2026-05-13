"""Telegram Stars (XTR) credit grant helper.

The bot does not go through FastAPI for Stars purchases — the
``successful_payment`` Telegram update arrives directly to aiogram and
we credit the user via the ORM session.  Idempotency is enforced by
storing ``telegram_payment_charge_id`` in :class:`CreditTransaction`'s
``payment_id`` column with a ``stars:`` prefix.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.models.db import CreditTransaction, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

STARS_PAYMENT_PREFIX = "stars:"


def _format_payment_id(charge_id: str) -> str:
    """Namespaced payment_id for Stars charges.

    Telegram ``telegram_payment_charge_id`` values are opaque strings —
    we prefix them with ``stars:`` so they cannot collide with YooKassa
    UUIDs or Xsolla transaction IDs in the same ``credit_transactions``
    table.
    """
    return f"{STARS_PAYMENT_PREFIX}{charge_id}"


async def record_stars_purchase(
    db: "AsyncSession",
    *,
    user_id: str | _uuid.UUID,
    pack_qty: int,
    charge_id: str,
    redis: "Redis | None" = None,
) -> dict:
    """Idempotently credit ``pack_qty`` to ``user_id`` for a Stars charge.

    Returns a status dict matching :func:`_grant_purchase_credits`:

    - ``{"status": "duplicate"}`` — same ``charge_id`` already processed.
    - ``{"status": "ok", "image_credits": …}`` — credits granted.
    - ``{"status": "error", "detail": …}`` — non-recoverable.
    """
    if pack_qty <= 0:
        return {"status": "error", "detail": "invalid pack_qty"}
    if not charge_id:
        return {"status": "error", "detail": "missing charge_id"}

    payment_id = _format_payment_id(charge_id)

    existing = await db.execute(
        select(CreditTransaction).where(CreditTransaction.payment_id == payment_id)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info("Duplicate Stars charge %s, skipping", charge_id)
        return {"status": "duplicate"}

    if isinstance(user_id, str):
        try:
            uid = _uuid.UUID(user_id)
        except (ValueError, TypeError):
            return {"status": "error", "detail": "invalid user_id"}
    else:
        uid = user_id

    user = await db.get(User, uid)
    if user is None:
        logger.error("Stars purchase: user %s not found (charge=%s)", uid, charge_id)
        return {"status": "error", "detail": "user not found"}

    user.image_credits += pack_qty
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=pack_qty,
            balance_after=user.image_credits,
            tx_type="purchase",
            payment_id=payment_id,
        )
    )
    await db.commit()

    logger.info(
        "Stars credits added: user=%s +%d credits, new_balance=%d, charge=%s",
        user.id,
        pack_qty,
        user.image_credits,
        charge_id,
    )

    if redis is not None:
        try:
            await redis.publish(
                f"ratemeai:payment_done:{user.id}",
                f"{pack_qty}:{user.image_credits}",
            )
        except Exception:
            logger.debug("Stars payment redis publish failed", exc_info=True)

    return {"status": "ok", "image_credits": user.image_credits}
