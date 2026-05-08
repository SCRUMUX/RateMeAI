"""Payment providers: YooKassa (edge) and Xsolla (primary)."""

from __future__ import annotations

from src.config import settings

from .credit_packs import CreditPack, get_credit_packs, pack_by_quantity, _pack_by_quantity
from .yookassa_provider import fetch_payment


async def create_payment(
    user_id: str,
    pack_qty: int,
    *,
    return_channel: str = "telegram",
):
    """Dispatch to the configured provider for this deployment."""
    if settings.payment_provider == "yookassa":
        from .yookassa_provider import create_payment as _create

        return await _create(user_id, pack_qty, return_channel=return_channel)
    from .xsolla_provider import create_payment as _create_x

    return await _create_x(user_id, pack_qty, return_channel=return_channel)


__all__ = [
    "CreditPack",
    "_pack_by_quantity",
    "create_payment",
    "fetch_payment",
    "get_credit_packs",
    "pack_by_quantity",
]
