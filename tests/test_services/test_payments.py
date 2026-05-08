"""Unit tests for payment pack helpers."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from src.services.payments import CreditPack, get_credit_packs, pack_by_quantity


def test_get_credit_packs_parses_rub():
    with patch("src.services.payments.credit_packs.settings") as mock_s:
        mock_s.payment_provider = "yookassa"
        mock_s.credit_packs = "5:150,25:300,100:900"
        mock_s.credit_packs_usd = ""
        packs = get_credit_packs()
        assert len(packs) == 3
        assert packs[0] == CreditPack(quantity=5, price=Decimal("150"), currency="RUB")
        assert packs[1] == CreditPack(quantity=25, price=Decimal("300"), currency="RUB")
        assert packs[2] == CreditPack(quantity=100, price=Decimal("900"), currency="RUB")


def test_get_credit_packs_parses_usd():
    with patch("src.services.payments.credit_packs.settings") as mock_s:
        mock_s.payment_provider = "xsolla"
        mock_s.credit_packs = ""
        mock_s.credit_packs_usd = "5:3.27,10:5.5"
        packs = get_credit_packs()
        assert len(packs) == 2
        assert packs[0].currency == "USD"
        assert packs[0].price == Decimal("3.27")


def test_get_credit_packs_handles_empty():
    with patch("src.services.payments.credit_packs.settings") as mock_s:
        mock_s.payment_provider = "yookassa"
        mock_s.credit_packs = ""
        assert get_credit_packs() == []


def test_pack_by_quantity_found():
    with patch("src.services.payments.credit_packs.settings") as mock_s:
        mock_s.payment_provider = "yookassa"
        mock_s.credit_packs = "5:150,25:300"
        pack = pack_by_quantity(25)
        assert pack is not None
        assert pack.quantity == 25


def test_pack_by_quantity_not_found():
    with patch("src.services.payments.credit_packs.settings") as mock_s:
        mock_s.payment_provider = "yookassa"
        mock_s.credit_packs = "5:150"
        assert pack_by_quantity(99) is None


def test_credit_pack_label_rub():
    p = CreditPack(quantity=5, price=Decimal("227"), currency="RUB")
    assert "5" in p.label
    assert "227" in p.label
    assert "₽" in p.label
    assert p.price_rub == 227


def test_credit_pack_label_usd():
    p = CreditPack(quantity=5, price=Decimal("3.27"), currency="USD")
    assert "$3.27" in p.label or "3.27" in p.label
