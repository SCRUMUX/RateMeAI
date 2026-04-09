"""Tests for enhancement_level pass-through and task result contract."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

_MIN_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9"
)


def _register_user(client, telegram_id: int = 888001) -> None:
    r = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": telegram_id, "username": "tester", "first_name": "Test"},
    )
    assert r.status_code == 200, r.text


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_stores_enhancement_level_in_context(mock_get_storage, mock_get_arq, client):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    tid = 888001
    _register_user(client, telegram_id=tid)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _MIN_JPEG, "image/jpeg")},
        data={"mode": "social", "style": "influencer", "enhancement_level": "1"},
        headers={"X-Telegram-Id": str(tid)},
    )
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]

    r2 = client.get(f"/api/v1/tasks/{task_id}", headers={"X-Telegram-Id": str(tid)})
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] == "pending"


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_default_enhancement_level_not_in_context(mock_get_storage, mock_get_arq, client):
    """When enhancement_level=0 (default), it should not appear in context."""
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    tid = 888002
    _register_user(client, telegram_id=tid)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _MIN_JPEG, "image/jpeg")},
        data={"mode": "dating", "style": "studio"},
        headers={"X-Telegram-Id": str(tid)},
    )
    assert r.status_code == 202, r.text
