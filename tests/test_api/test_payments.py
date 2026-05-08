"""Tests for payment endpoints (YooKassa on edge, Xsolla on primary)."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, patch


def _register_user(client, telegram_id: int = 888001) -> tuple[str, str]:
    """Register user and return (user_id, session_token)."""
    r = client.post(
        "/api/v1/auth/telegram",
        json={
            "telegram_id": telegram_id,
            "username": "pay_tester",
            "first_name": "Pay",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return data["user_id"], data["session_token"]


def _webhook_body(payment_id: str, user_id: str, pack_qty: int) -> dict:
    return {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": payment_id,
            "status": "succeeded",
            "metadata": {
                "user_id": user_id,
                "pack_qty": str(pack_qty),
            },
        },
    }


@patch("src.api.v1.payments._notify_user_channels", new_callable=AsyncMock)
@patch("src.api.v1.payments._is_trusted_ip", return_value=True)
def test_webhook_credits_user(mock_ip, mock_notify, edge_client):
    tg_id = 888001
    user_id, token = _register_user(edge_client, tg_id)

    body = _webhook_body("pay_test_001", user_id, 5)
    r = edge_client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert data["credits_added"] == 5

    r2 = edge_client.get(
        "/api/v1/payments/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["image_credits"] >= 5


@patch("src.api.v1.payments._notify_user_channels", new_callable=AsyncMock)
@patch("src.api.v1.payments._is_trusted_ip", return_value=True)
def test_webhook_duplicate_rejected(mock_ip, mock_notify, edge_client):
    tg_id = 888002
    user_id, _token = _register_user(edge_client, tg_id)

    body = _webhook_body("pay_dup_001", user_id, 10)
    r1 = edge_client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r1.status_code == 200
    assert r1.json()["status"] == "ok"

    r2 = edge_client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


def test_webhook_ignored_non_succeeded(edge_client):
    body = {
        "type": "notification",
        "event": "payment.waiting_for_capture",
        "object": {"id": "pay_ign_001", "status": "waiting_for_capture"},
    }
    r = edge_client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


@patch(
    "src.api.v1.payments._verify_payment_server_side",
    new_callable=AsyncMock,
    return_value=None,
)
@patch("src.api.v1.payments._is_trusted_ip", return_value=False)
def test_webhook_untrusted_ip_rejected(mock_ip, mock_verify, edge_client):
    body = _webhook_body("pay_untrust_001", "00000000-0000-0000-0000-000000000099", 5)
    r = edge_client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r.status_code == 403


def test_balance_missing_header(client):
    r = client.get("/api/v1/payments/balance")
    assert r.status_code == 401


def test_balance_unknown_user(client):
    r = client.get(
        "/api/v1/payments/balance",
        headers={"Authorization": "Bearer invalid_token_for_unknown_user"},
    )
    assert r.status_code == 401


# --- Guard: на primary-домене YooKassa недоступна --------------------------------


def test_webhook_returns_410_on_primary(client):
    """YooKassa webhook must not run on primary."""
    body = _webhook_body(
        "pay_primary_blocked", "00000000-0000-0000-0000-000000000000", 5
    )
    r = client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r.status_code == 410, r.text
    assert r.json()["detail"] == "payments_disabled_on_primary"


def test_xsolla_webhook_returns_410_on_edge(edge_client):
    body = {"notification_type": "payment"}
    r = edge_client.post("/api/v1/payments/xsolla/webhook", json=body)
    assert r.status_code == 410
    assert r.json()["detail"] == "xsolla_disabled_on_edge"


@patch(
    "src.services.payments.xsolla_provider.create_payment",
    new_callable=AsyncMock,
    return_value=("tok_unit", "https://secure.xsolla.com/paystation4/?token=tok_unit"),
)
def test_create_payment_primary_xsolla(mock_xsolla, primary_payment_client):
    _, token = _register_user(primary_payment_client, telegram_id=888_888)
    r = primary_payment_client.post(
        "/api/v1/payments/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"pack_qty": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["payment_id"] == "tok_unit"
    assert "secure.xsolla.com" in data["confirmation_url"]
    mock_xsolla.assert_awaited()


def test_list_packs_primary(primary_payment_client):
    r = primary_payment_client.get("/api/v1/payments/packs")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "xsolla"
    assert body["currency"] == "USD"
    assert len(body["packs"]) >= 1


def test_list_packs_edge(edge_client):
    r = edge_client.get("/api/v1/payments/packs")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "yookassa"
    assert body["currency"] == "RUB"


@patch("src.api.v1.payments._notify_user_channels", new_callable=AsyncMock)
def test_xsolla_webhook_credits_user(mock_notify, primary_payment_client):
    tg_id = 888_333
    user_id, _token = _register_user(primary_payment_client, tg_id)
    body = {
        "notification_type": "payment",
        "transaction": {"id": 990_001, "status": "done"},
        "custom_parameters": {"user_id": user_id, "pack_qty": "10"},
    }
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    secret = "unit-test-xsolla-secret"
    sig = hashlib.sha1(raw + secret.encode()).hexdigest()
    r = primary_payment_client.post(
        "/api/v1/payments/xsolla/webhook",
        content=raw,
        headers={
            "Authorization": f"Signature {sig}",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"


@patch("src.api.v1.payments._notify_user_channels", new_callable=AsyncMock)
def test_xsolla_webhook_bad_signature(mock_notify, primary_payment_client):
    tg_id = 888_334
    user_id, _token = _register_user(primary_payment_client, tg_id)
    body = {
        "notification_type": "payment",
        "transaction": {"id": 990_002, "status": "done"},
        "custom_parameters": {"user_id": user_id, "pack_qty": "5"},
    }
    raw = json.dumps(body).encode("utf-8")
    r = primary_payment_client.post(
        "/api/v1/payments/xsolla/webhook",
        content=raw,
        headers={"Authorization": "Signature deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 403
