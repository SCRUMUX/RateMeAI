"""Tests for Yandex ID and VK ID OAuth endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.channels.yandex_auth import YandexUser
from src.channels.vk_id_auth import VKIDUser
from src.config import settings


@pytest.fixture(autouse=True)
def _ensure_oauth_creds(monkeypatch):
    """Provide non-empty OAuth credentials so the 503-guards don't trip.

    Both ``/auth/yandex/init`` and ``/auth/vk-id/init`` raise HTTP 503
    when their respective ``*_CLIENT_ID``/``SECRET`` settings are empty
    (production safety: missing creds → user sees "OAuth not
    configured" instead of a confusing provider error page). Tests
    don't load the production ``.env``, so the values are blank by
    default — patch them to dummies that satisfy the guard.
    """
    monkeypatch.setattr(settings, "yandex_client_id", "test-yandex-id", raising=False)
    monkeypatch.setattr(
        settings, "yandex_client_secret", "test-yandex-secret", raising=False
    )
    monkeypatch.setattr(settings, "vk_id_app_id", "test-vk-id", raising=False)
    monkeypatch.setattr(settings, "vk_id_app_secret", "test-vk-secret", raising=False)


# ── Yandex ID ──


def test_yandex_init_returns_authorize_url(client):
    r = client.post("/api/v1/auth/yandex/init", json={"device_id": "dev-001"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "authorize_url" in data
    url = data["authorize_url"]
    assert "oauth.yandex.com/authorize" in url
    assert "response_type=code" in url
    assert "state=" in url


def test_yandex_callback_invalid_state(client):
    r = client.get(
        "/api/v1/auth/yandex/callback", params={"code": "abc", "state": "bad"}
    )
    assert r.status_code == 400


@patch(
    "src.channels.yandex_auth.get_user_info",
    new_callable=AsyncMock,
    return_value=YandexUser(
        id="ya_123", login="testuser", display_name="Test", default_email="test@ya.ru"
    ),
)
@patch(
    "src.channels.yandex_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="fake_access_token",
)
def test_yandex_callback_success(mock_exchange, mock_userinfo, client):
    init = client.post("/api/v1/auth/yandex/init", json={"device_id": "dev-ya-001"})
    assert init.status_code == 200
    url = init.json()["authorize_url"]
    state = _extract_param(url, "state")

    r = client.get(
        "/api/v1/auth/yandex/callback",
        params={"code": "auth_code_ya", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 307
    location = r.headers["location"]
    assert "/auth/callback" in location
    assert "token=" in location
    assert "provider=yandex" in location
    assert "user_id=" in location


@patch(
    "src.channels.yandex_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="",
)
def test_yandex_callback_token_exchange_fails(mock_exchange, client):
    init = client.post("/api/v1/auth/yandex/init", json={})
    state = _extract_param(init.json()["authorize_url"], "state")
    r = client.get(
        "/api/v1/auth/yandex/callback",
        params={"code": "bad_code", "state": state},
    )
    assert r.status_code == 401


# ── VK ID ──


def test_vk_id_init_returns_authorize_url(client):
    r = client.post("/api/v1/auth/vk-id/init", json={"device_id": "dev-vk-001"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "authorize_url" in data
    url = data["authorize_url"]
    assert "id.vk.ru/authorize" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "device_id" not in url, (
        "device_id must not be in authorize URL per VK ID docs"
    )


def test_vk_id_callback_invalid_state(client):
    r = client.get(
        "/api/v1/auth/vk-id/callback", params={"code": "abc", "state": "bad"}
    )
    assert r.status_code == 400


@patch(
    "src.channels.vk_id_auth.get_user_info",
    new_callable=AsyncMock,
    return_value=VKIDUser(
        user_id="vk_456", first_name="Ivan", last_name="Petrov", email="ivan@vk.com"
    ),
)
@patch(
    "src.channels.vk_id_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="fake_vk_token",
)
def test_vk_id_callback_success(mock_exchange, mock_userinfo, client):
    init = client.post("/api/v1/auth/vk-id/init", json={"device_id": "dev-vk-002"})
    assert init.status_code == 200
    url = init.json()["authorize_url"]
    state = _extract_param(url, "state")

    r = client.get(
        "/api/v1/auth/vk-id/callback",
        params={"code": "auth_code_vk", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 307
    location = r.headers["location"]
    assert "/auth/callback" in location
    assert "token=" in location
    assert "provider=vk_id" in location
    assert "user_id=" in location


@patch(
    "src.channels.vk_id_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="",
)
def test_vk_id_callback_token_exchange_fails(mock_exchange, client):
    init = client.post("/api/v1/auth/vk-id/init", json={})
    state = _extract_param(init.json()["authorize_url"], "state")
    r = client.get(
        "/api/v1/auth/vk-id/callback",
        params={"code": "bad_code", "state": state},
    )
    assert r.status_code == 401


# ── Idempotency ──


@patch(
    "src.channels.yandex_auth.get_user_info",
    new_callable=AsyncMock,
    return_value=YandexUser(
        id="ya_repeat", login="repeat", display_name="Repeat", default_email=None
    ),
)
@patch(
    "src.channels.yandex_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="tok",
)
def test_yandex_callback_idempotent_user(mock_exchange, mock_userinfo, client):
    """Same yandex id produces the same internal user."""
    user_ids = []
    for _ in range(2):
        init = client.post("/api/v1/auth/yandex/init", json={})
        state = _extract_param(init.json()["authorize_url"], "state")
        r = client.get(
            "/api/v1/auth/yandex/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )
        location = r.headers["location"]
        user_ids.append(_extract_param(location, "user_id"))
    assert user_ids[0] == user_ids[1]


# ── return_path round-trip ──
#
# Stage 0 of the visa OAuth fix (1.57.0): the SPA passes a relative
# ``return_path`` (e.g. ``/visa/schengen``) when starting OAuth. The
# backend stores it in Redis next to the ``state`` token and re-emits
# it as a query parameter on the final redirect to ``/auth/callback``,
# so the SPA can navigate the user back to the original landing even
# when the OAuth provider sends them through a different origin.


@patch(
    "src.channels.yandex_auth.get_user_info",
    new_callable=AsyncMock,
    return_value=YandexUser(
        id="ya_return", login="return", display_name="Return", default_email=None
    ),
)
@patch(
    "src.channels.yandex_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="tok",
)
def test_yandex_callback_propagates_return_path(mock_exchange, mock_userinfo, client):
    init = client.post(
        "/api/v1/auth/yandex/init",
        json={"device_id": "dev-return", "return_path": "/visa/schengen"},
    )
    assert init.status_code == 200, init.text
    state = _extract_param(init.json()["authorize_url"], "state")

    r = client.get(
        "/api/v1/auth/yandex/callback",
        params={"code": "c-return", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 307
    location = r.headers["location"]
    assert _extract_param(location, "return_path") == "/visa/schengen"


@patch(
    "src.channels.yandex_auth.get_user_info",
    new_callable=AsyncMock,
    return_value=YandexUser(
        id="ya_dirty", login="dirty", display_name="Dirty", default_email=None
    ),
)
@patch(
    "src.channels.yandex_auth.exchange_code",
    new_callable=AsyncMock,
    return_value="tok",
)
def test_yandex_callback_strips_unsafe_return_path(mock_exchange, mock_userinfo, client):
    """Absolute URLs and protocol-relative paths must be dropped to
    prevent open-redirect via the OAuth round-trip."""
    init = client.post(
        "/api/v1/auth/yandex/init",
        json={"return_path": "https://evil.example.com/phish"},
    )
    state = _extract_param(init.json()["authorize_url"], "state")

    r = client.get(
        "/api/v1/auth/yandex/callback",
        params={"code": "c-dirty", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 307
    location = r.headers["location"]
    assert "return_path=" not in location, location


# ── helpers ──


def _extract_param(url: str, key: str) -> str:
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    return parse_qs(parsed.query).get(key, [""])[0]
