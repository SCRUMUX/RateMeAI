"""Tests for YooKassa webhook / payment endpoints.

Платёжный контур живёт только на RU-edge (YooKassa принимает вебхуки только
с российских IP), поэтому все тесты webhook/create работают через
``edge_client`` (monkeypatch ``deployment_mode=edge``). Отдельные тесты ниже
подтверждают, что на primary те же эндпоинты отдают 410.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch


def _register_user(client, telegram_id: int = 888001) -> tuple[str, str]:
    """Register user and return (user_id, session_token)."""
    r = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": telegram_id, "username": "pay_tester", "first_name": "Pay"},
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


@patch("src.api.v1.payments._verify_payment_server_side", new_callable=AsyncMock, return_value=None)
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
    """На primary-бэкенде (DEPLOYMENT_MODE!=edge) webhook YooKassa отключён.

    Любой POST должен отвергаться с 410 Gone ещё до разбора тела — иначе
    любой может засыпать бэкенд фейковыми событиями, а в самых неудачных
    раскладах (тестовые креды) это приведёт к зачислению кредитов.
    """
    body = _webhook_body("pay_primary_blocked", "00000000-0000-0000-0000-000000000000", 5)
    r = client.post("/api/v1/payments/yookassa/webhook", json=body)
    assert r.status_code == 410, r.text
    assert r.json()["detail"] == "payments_disabled_on_primary"


def test_create_payment_returns_410_on_primary(client):
    """POST /api/v1/payments/create на primary отвечает 410 + machine-code.

    Web / bot по этому коду понимают, что оплата доступна только через
    RU-домен, и редиректят пользователя.
    """
    _, token = _register_user(client, telegram_id=888_777)
    r = client.post(
        "/api/v1/payments/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"pack_qty": 5},
    )
    assert r.status_code == 410, r.text
    assert r.json()["detail"] == "payments_disabled_on_primary"
    assert r.headers.get("X-Payments-Channel") == "edge-only"
