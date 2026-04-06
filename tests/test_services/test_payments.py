"""Unit tests for payment service helpers."""
from __future__ import annotations

from unittest.mock import patch

from src.services.payments import get_credit_packs, _pack_by_quantity, CreditPack


def test_get_credit_packs_parses_config():
    with patch("src.services.payments.settings") as mock_s:
        mock_s.credit_packs = "5:150,25:300,100:900"
        packs = get_credit_packs()
        assert len(packs) == 3
        assert packs[0] == CreditPack(quantity=5, price_rub=150)
        assert packs[1] == CreditPack(quantity=25, price_rub=300)
        assert packs[2] == CreditPack(quantity=100, price_rub=900)


def test_get_credit_packs_handles_empty():
    with patch("src.services.payments.settings") as mock_s:
        mock_s.credit_packs = ""
        assert get_credit_packs() == []


def test_pack_by_quantity_found():
    with patch("src.services.payments.settings") as mock_s:
        mock_s.credit_packs = "5:150,25:300"
        pack = _pack_by_quantity(25)
        assert pack is not None
        assert pack.quantity == 25


def test_pack_by_quantity_not_found():
    with patch("src.services.payments.settings") as mock_s:
        mock_s.credit_packs = "5:150"
        assert _pack_by_quantity(99) is None


def test_credit_pack_label():
    p = CreditPack(quantity=5, price_rub=150)
    assert "5" in p.label
    assert "150 ₽" in p.label
