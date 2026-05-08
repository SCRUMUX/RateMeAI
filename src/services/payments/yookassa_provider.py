"""YooKassa payment integration (RU edge)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from yookassa import Configuration, Payment

from src.config import settings

logger = logging.getLogger(__name__)


def _ensure_configured() -> None:
    if not Configuration.account_id:
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key


def _resolve_return_url(channel: str) -> str:
    if channel == "web" and settings.web_base_url:
        return f"{settings.web_base_url.rstrip('/')}/payment-success"
    return settings.yookassa_return_url.format(
        bot_username=settings.telegram_bot_username,
    )


async def create_payment(
    user_id: str,
    pack_qty: int,
    *,
    return_channel: str = "telegram",
):
    """Create a YooKassa payment. Returns (payment_id, confirmation_url) or None."""
    from .credit_packs import pack_by_quantity

    pack = pack_by_quantity(pack_qty)
    if pack is None:
        logger.error("Unknown pack quantity: %s", pack_qty)
        return None

    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        logger.error("YooKassa credentials not configured")
        return None

    _ensure_configured()

    return_url = _resolve_return_url(return_channel)

    rub_amount = int(pack.price)
    params = {
        "amount": {
            "value": f"{rub_amount}.00",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "capture": True,
        "description": f"RateMeAI: {pack.quantity} улучшений образа",
        "metadata": {
            "user_id": user_id,
            "pack_qty": str(pack.quantity),
        },
    }

    try:
        payment = await asyncio.to_thread(
            Payment.create,
            params,
            uuid.uuid4(),
        )
        url = payment.confirmation.confirmation_url
        logger.info(
            "Payment created: id=%s user=%s pack=%s url=%s",
            payment.id,
            user_id,
            pack_qty,
            url,
        )
        return payment.id, url
    except Exception:
        logger.exception("Failed to create YooKassa payment for user=%s", user_id)
        return None


async def fetch_payment(payment_id: str):
    """Retrieve a payment from YooKassa by id."""
    _ensure_configured()
    return await asyncio.to_thread(Payment.find_one, payment_id)
