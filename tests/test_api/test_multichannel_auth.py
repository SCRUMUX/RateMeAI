"""Tests for multi-channel authentication endpoints."""

from __future__ import annotations

from unittest.mock import patch


def test_auth_web_creates_user(client):
    r = client.post("/api/v1/auth/web", json={"device_id": "device-test-001"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "session_token" in data
    assert "user_id" in data
    assert "usage" in data


def test_auth_web_idempotent(client):
    r1 = client.post("/api/v1/auth/web", json={"device_id": "device-idem-001"})
    r2 = client.post("/api/v1/auth/web", json={"device_id": "device-idem-001"})
    assert r1.json()["user_id"] == r2.json()["user_id"]


def test_auth_ok_rejects_bad_sig(client):
    r = client.post(
        "/api/v1/auth/ok",
        json={
            "logged_user_id": "12345",
            "session_key": "sess_key",
            "auth_sig": "bad_sig",
        },
    )
    assert r.status_code == 401


@patch("src.channels.ok_auth.verify_ok_auth_sig", return_value=True)
def test_auth_ok_success(mock_verify, client):
    r = client.post(
        "/api/v1/auth/ok",
        json={
            "logged_user_id": "ok_user_001",
            "session_key": "sess",
            "auth_sig": "valid",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "session_token" in data
    assert "user_id" in data


def test_auth_vk_rejects_bad_params(client):
    r = client.post("/api/v1/auth/vk", json={"launch_params": "invalid"})
    assert r.status_code == 401


def test_bearer_token_auth(client):
    r = client.post("/api/v1/auth/web", json={"device_id": "bearer-test-001"})
    token = r.json()["session_token"]

    r2 = client.get(
        "/api/v1/payments/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert "image_credits" in r2.json()


def test_bearer_invalid_token(client):
    r = client.get(
        "/api/v1/payments/balance",
        headers={"Authorization": "Bearer totally_invalid_token"},
    )
    assert r.status_code == 401
