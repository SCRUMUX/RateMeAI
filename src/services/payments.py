"""YooKassa payment integration service."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from yookassa import Configuration, Payment

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreditPack:
    quantity: int
    price_rub: int

    @property
    def label(self) -> str:
        return f"{self.quantity} образов — {self.price_rub} ₽"


def get_credit_packs() -> list[CreditPack]:
    packs: list[CreditPack] = []
    for entry in settings.credit_packs.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        qty, price = entry.split(":", 1)
        packs.append(CreditPack(quantity=int(qty), price_rub=int(price)))
    return packs


def _pack_by_quantity(qty: int) -> CreditPack | None:
    for p in get_credit_packs():
        if p.quantity == qty:
            return p
    return None


def _ensure_configured() -> None:
    if not Configuration.account_id:
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key


async def create_payment(telegram_id: int, pack_qty: int) -> tuple[str, str] | None:
    """Create a YooKassa payment. Returns (payment_id, confirmation_url) or None."""
    pack = _pack_by_quantity(pack_qty)
    if pack is None:
        logger.error("Unknown pack quantity: %s", pack_qty)
        return None

    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        logger.error("YooKassa credentials not configured")
        return None

    _ensure_configured()

    return_url = settings.yookassa_return_url.format(
        bot_username=settings.telegram_bot_username,
    )

    params = {
        "amount": {
            "value": f"{pack.price_rub}.00",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "capture": True,
        "description": f"RateMeAI: {pack.quantity} улучшений образа",
        "metadata": {
            "telegram_id": str(telegram_id),
            "pack_qty": str(pack.quantity),
        },
    }

    try:
        payment = await asyncio.to_thread(
            Payment.create, params, uuid.uuid4(),
        )
        url = payment.confirmation.confirmation_url
        logger.info(
            "Payment created: id=%s tg=%s pack=%s url=%s",
            payment.id, telegram_id, pack_qty, url,
        )
        return payment.id, url
    except Exception:
        logger.exception("Failed to create YooKassa payment for tg=%s", telegram_id)
        return None


async def fetch_payment(payment_id: str):
    """Retrieve a payment from YooKassa by id."""
    _ensure_configured()
    return await asyncio.to_thread(Payment.find_one, payment_id)
