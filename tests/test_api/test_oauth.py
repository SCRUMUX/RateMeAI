"""Tests for Yandex ID and VK ID OAuth endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from src.channels.yandex_auth import YandexUser
from src.channels.vk_id_auth import VKIDUser


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


# ── helpers ──


def _extract_param(url: str, key: str) -> str:
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    return parse_qs(parsed.query).get(key, [""])[0]
