"""YooKassa payment webhook and API endpoints."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_redis
from src.config import settings
from src.models.db import User, CreditTransaction

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/yookassa/webhook")
async def yookassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Handle YooKassa payment.succeeded notification.

    YooKassa sends a JSON body like:
    {
      "type": "notification",
      "event": "payment.succeeded",
      "object": { ...payment object... }
    }
    """
    body = await request.json()
    event = body.get("event", "")
    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id", "unknown")
    status = payment_obj.get("status", "")

    logger.info("YooKassa webhook: event=%s payment=%s status=%s", event, payment_id, status)

    if event != "payment.succeeded" or status != "succeeded":
        return {"status": "ignored", "event": event}

    metadata = payment_obj.get("metadata", {})
    telegram_id_str = metadata.get("telegram_id")
    pack_qty_str = metadata.get("pack_qty")

    if not telegram_id_str or not pack_qty_str:
        logger.warning("Webhook missing metadata: payment=%s meta=%s", payment_id, metadata)
        return {"status": "error", "detail": "missing metadata"}

    telegram_id = int(telegram_id_str)
    pack_qty = int(pack_qty_str)

    existing = await db.execute(
        select(CreditTransaction).where(CreditTransaction.payment_id == payment_id)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info("Duplicate webhook for payment=%s, skipping", payment_id)
        return {"status": "duplicate"}

    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.error("User not found for telegram_id=%s payment=%s", telegram_id, payment_id)
        raise HTTPException(status_code=404, detail="User not found")

    user.image_credits += pack_qty
    db.add(CreditTransaction(
        user_id=user.id,
        amount=pack_qty,
        balance_after=user.image_credits,
        tx_type="purchase",
        payment_id=payment_id,
    ))
    await db.commit()

    logger.info(
        "Credits added: user=%s tg=%s +%d credits, new_balance=%d, payment=%s",
        user.id, telegram_id, pack_qty, user.image_credits, payment_id,
    )

    try:
        await redis.publish(
            f"ratemeai:payment_done:{telegram_id}",
            f"{pack_qty}:{user.image_credits}",
        )
    except Exception:
        logger.warning("Failed to publish payment notification for tg=%s", telegram_id)

    await _notify_telegram(telegram_id, pack_qty, user.image_credits)

    return {"status": "ok", "credits_added": pack_qty, "balance": user.image_credits}


@router.get("/balance")
async def get_balance(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get user's credit balance by telegram_id header."""
    tg_id = request.headers.get("X-Telegram-Id")
    if not tg_id:
        raise HTTPException(status_code=401, detail="X-Telegram-Id required")

    result = await db.execute(select(User).where(User.telegram_id == int(tg_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {"telegram_id": int(tg_id), "image_credits": user.image_credits}


async def _notify_telegram(telegram_id: int, pack_qty: int, new_balance: int) -> None:
    """Send a direct Telegram message to user about successful payment."""
    token = settings.telegram_bot_token
    if not token:
        return
    text = (
        f"✅ Оплата прошла успешно!\n\n"
        f"Начислено: *{pack_qty} генераций*\n"
        f"Баланс: *{new_balance} генераций*\n\n"
        f"Отправь фото для начала!"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "Markdown",
            })
            if resp.status_code != 200:
                logger.warning("Telegram notify failed: %s %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("Failed to send Telegram payment notification to %s", telegram_id)
