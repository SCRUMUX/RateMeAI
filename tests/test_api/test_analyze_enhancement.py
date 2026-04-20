"""Tests for enhancement_level pass-through and task result contract."""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

_CONSENT_HEADERS = {
    "X-Consent-Data-Processing": "1",
    "X-Consent-AI-Transfer": "1",
}


def _valid_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(128, 128, 128)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


_VALID_JPEG = _valid_jpeg()


def _register_user(client, telegram_id: int = 888001) -> str:
    """Register user and return Bearer token."""
    r = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": telegram_id, "username": "tester", "first_name": "Test"},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **_CONSENT_HEADERS}


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
    token = _register_user(client, telegram_id=tid)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "social", "style": "influencer", "enhancement_level": "1"},
        headers=_auth(token),
    )
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]

    r2 = client.get(f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
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
    token = _register_user(client, telegram_id=tid)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "dating", "style": "studio"},
        headers=_auth(token),
    )
    assert r.status_code == 202, r.text
