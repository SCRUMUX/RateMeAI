"""Integration tests for ``/api/v1/internal/bot/*`` endpoints.

These require Postgres + Redis (same as the other integration suites);
the shared ``client`` fixture skips when those are absent.

Coverage:
- ``X-Internal-Key`` auth: 403 without it, 200 with the right key.
- ``GET /users/{tg_id}/profile``: shape, 404 for unknown tg_id.
- ``POST /stars/grant``: 404 for unknown tg_id, idempotent on
  ``telegram_payment_charge_id``.
"""

from __future__ import annotations

import uuid as _uuid

import pytest


_INTERNAL_KEY = "unit-test-internal-key"


@pytest.fixture
def primary_client(client, monkeypatch):
    """``client`` with a known ``internal_api_key`` set."""
    from src.config import settings

    monkeypatch.setattr(settings, "internal_api_key", _INTERNAL_KEY)
    return client


@pytest.fixture
def tg_user(primary_client):
    """Create a Telegram-linked user via the existing auth endpoint."""
    import secrets

    tg_id = secrets.randbits(40) + 1  # avoid collision across runs
    resp = primary_client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": tg_id, "username": "stars_test"},
    )
    assert resp.status_code == 200, resp.text
    return tg_id, resp.json()["user_id"]


def test_internal_bot_requires_key(primary_client, tg_user):
    tg_id, _user_id = tg_user
    resp = primary_client.get(f"/api/v1/internal/bot/users/{tg_id}/profile")
    # Without the header FastAPI raises 422 (header required); with a
    # wrong value we get 403.  Both are "non-authorised" outcomes; we
    # accept either to keep the test resilient to future signature
    # tweaks.
    assert resp.status_code in (403, 422)

    resp = primary_client.get(
        f"/api/v1/internal/bot/users/{tg_id}/profile",
        headers={"X-Internal-Key": "wrong"},
    )
    assert resp.status_code == 403


def test_get_bot_user_profile_returns_credits(primary_client, tg_user):
    tg_id, user_id = tg_user
    resp = primary_client.get(
        f"/api/v1/internal/bot/users/{tg_id}/profile",
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] == user_id
    assert isinstance(data["image_credits"], int)
    assert "username" in data
    assert "language_code" in data


def test_get_bot_user_profile_404_for_unknown_tg(primary_client):
    resp = primary_client.get(
        "/api/v1/internal/bot/users/999999999999/profile",
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert resp.status_code == 404


def test_stars_grant_idempotent(primary_client, tg_user):
    tg_id, user_id = tg_user
    charge_id = f"unit-test-{_uuid.uuid4().hex[:10]}"
    payload = {
        "telegram_id": tg_id,
        "pack_qty": 5,
        "telegram_payment_charge_id": charge_id,
    }

    first = primary_client.post(
        "/api/v1/internal/bot/stars/grant",
        json=payload,
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ok"
    first_balance = first.json()["image_credits"]

    second = primary_client.post(
        "/api/v1/internal/bot/stars/grant",
        json=payload,
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate"

    # Balance must not have moved on the replay.
    probe = primary_client.get(
        f"/api/v1/internal/bot/users/{tg_id}/profile",
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert probe.status_code == 200
    assert probe.json()["image_credits"] == first_balance


def test_stars_grant_404_for_unknown_user(primary_client):
    resp = primary_client.post(
        "/api/v1/internal/bot/stars/grant",
        json={
            "telegram_id": 8888888888,
            "pack_qty": 5,
            "telegram_payment_charge_id": "ignored",
        },
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert resp.status_code == 404
