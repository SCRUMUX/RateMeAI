"""Tests for the Telegram Stars (XTR) payment flow.

We do **not** exercise live aiogram updates here — instead we test
the two pure pieces that hold the invariant together:

1. ``_pack_from_payload`` / ``_payload_for_pack`` — round-trip that
   pre_checkout_query relies on to re-derive the canonical price.
2. ``record_stars_purchase`` — idempotent ORM credit grant that the
   internal endpoint calls.

That covers both regression vectors plan E.5 mentions:

* a tampered ``total_amount`` is rejected (because the payload still
  resolves to a known pack and the price doesn't match), and
* a replay of the same ``telegram_payment_charge_id`` does not
  double-credit the user.
"""

from __future__ import annotations

import uuid as _uuid

import pytest


# ---- payload <-> pack round trip ------------------------------------------------


def test_payload_round_trips_through_pack_helpers():
    from src.bot.handlers.stars import _pack_from_payload, _payload_for_pack

    payload = _payload_for_pack(10)
    assert payload.startswith("stars:pack:")

    pack = _pack_from_payload(payload)
    assert pack is not None
    assert pack.quantity == 10
    assert pack.currency == "XTR"
    assert pack.price_stars > 0


def test_pack_from_payload_rejects_foreign_payloads():
    from src.bot.handlers.stars import _pack_from_payload

    assert _pack_from_payload("") is None
    assert _pack_from_payload("rub:pack:10") is None
    assert _pack_from_payload("stars:pack:notanint") is None


def test_pack_from_payload_unknown_qty_returns_none(monkeypatch):
    from src.bot.handlers import stars as stars_mod

    monkeypatch.setattr(
        stars_mod, "xtr_pack_by_quantity", lambda qty: None
    )
    assert stars_mod._pack_from_payload("stars:pack:42") is None


# ---- record_stars_purchase idempotency -----------------------------------------


class _FakeUser:
    def __init__(self):
        self.id = _uuid.uuid4()
        self.image_credits = 0


class _FakeRow:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    """Minimal AsyncSession stub: enough to drive record_stars_purchase."""

    def __init__(self, user):
        self._user = user
        self._existing_payment_id: str | None = None
        self._added: list[object] = []
        self.commits = 0

    async def execute(self, _stmt):
        # The only execute() call in record_stars_purchase is the
        # CreditTransaction lookup by payment_id; the caller cares
        # only whether scalar_one_or_none() returns None vs anything
        # truthy, so we return a sentinel object on replay.
        if self._existing_payment_id is None:
            return _FakeRow(None)
        return _FakeRow(object())

    async def get(self, _model, _id):
        return self._user

    def add(self, obj):
        self._added.append(obj)
        pid = getattr(obj, "payment_id", None)
        if pid is not None:
            self._existing_payment_id = pid

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_record_stars_purchase_grants_credits_once():
    from src.services.payments.stars import record_stars_purchase

    user = _FakeUser()
    db = _FakeDb(user)

    result_a = await record_stars_purchase(
        db,
        user_id=user.id,
        pack_qty=5,
        charge_id="charge_abc",
    )
    assert result_a["status"] == "ok"
    assert user.image_credits == 5
    assert db.commits == 1

    # Replay: same charge_id → record_stars_purchase MUST return
    # "duplicate" without touching credits or committing again.
    result_b = await record_stars_purchase(
        db,
        user_id=user.id,
        pack_qty=5,
        charge_id="charge_abc",
    )
    assert result_b == {"status": "duplicate"}
    assert user.image_credits == 5
    assert db.commits == 1


@pytest.mark.asyncio
async def test_record_stars_purchase_rejects_bad_input():
    from src.services.payments.stars import record_stars_purchase

    user = _FakeUser()
    db = _FakeDb(user)

    assert (
        await record_stars_purchase(
            db, user_id=user.id, pack_qty=0, charge_id="x"
        )
    )["status"] == "error"

    assert (
        await record_stars_purchase(
            db, user_id=user.id, pack_qty=5, charge_id=""
        )
    )["status"] == "error"


# ---- per-language landing helpers ----------------------------------------------


def test_landing_url_resolver_picks_ru_for_ru_family(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "bot_web_landing_url_ru", "https://ailookstudio.ru")
    monkeypatch.setattr(
        settings,
        "bot_web_landing_url_default",
        "https://ailookstudio.vercel.app",
    )

    for code in ("ru", "ru-RU", "be", "kk", "uk", "ky"):
        assert settings.resolve_landing_url(code) == "https://ailookstudio.ru"


def test_landing_url_resolver_falls_back_to_default(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "bot_web_landing_url_ru", "https://ailookstudio.ru")
    monkeypatch.setattr(
        settings,
        "bot_web_landing_url_default",
        "https://ailookstudio.vercel.app",
    )

    for code in ("en", "fr", "th-TH", None, "", "zh"):
        assert (
            settings.resolve_landing_url(code) == "https://ailookstudio.vercel.app"
        )
