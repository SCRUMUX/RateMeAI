"""Smoke tests for Xsolla helper module."""

from __future__ import annotations

from src.services.payments import xsolla_provider as xp


def test_paystation_url_template_has_host():
    assert "secure.xsolla.com" in xp.PAYSTATION_URL
    assert "{token}" in xp.PAYSTATION_URL


def test_token_endpoint_pattern():
    assert "{merchant_id}" in xp.XSOLLA_TOKEN_URL
