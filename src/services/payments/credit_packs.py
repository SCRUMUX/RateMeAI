"""Credit pack parsing (RUB on edge, USD on primary)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from src.config import settings

Currency = Literal["RUB", "USD"]


@dataclass(frozen=True)
class CreditPack:
    quantity: int
    price: Decimal
    currency: Currency

    @property
    def label(self) -> str:
        if self.currency == "RUB":
            return f"{self.quantity} образов — {int(self.price)} ₽"
        normalized = self.price.quantize(Decimal("0.01"))
        amt = format(normalized, "f")
        return f"{self.quantity} photos — ${amt}"

    @property
    def price_rub(self) -> int:
        """Backward compat for callers that expect integer RUB."""
        if self.currency != "RUB":
            raise AttributeError("price_rub is only defined for RUB packs")
        return int(self.price)


def _parse_decimal(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _parse_packs_csv(csv: str, currency: Currency) -> list[CreditPack]:
    packs: list[CreditPack] = []
    for entry in csv.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        qty_str, price_str = entry.split(":", 1)
        try:
            qty = int(qty_str.strip())
        except ValueError:
            continue
        price = _parse_decimal(price_str)
        if price is None or qty <= 0 or price <= 0:
            continue
        packs.append(CreditPack(quantity=qty, price=price, currency=currency))
    return packs


def get_credit_packs() -> list[CreditPack]:
    if settings.payment_provider == "yookassa":
        return _parse_packs_csv(settings.credit_packs, "RUB")
    return _parse_packs_csv(settings.credit_packs_usd, "USD")


def pack_by_quantity(qty: int) -> CreditPack | None:
    for p in get_credit_packs():
        if p.quantity == qty:
            return p
    return None


# Legacy bot import name
_pack_by_quantity = pack_by_quantity
