from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

_CONSENT_HEADERS = {
    "X-Consent-Data-Processing": "1",
    "X-Consent-AI-Transfer": "1",
}


def _valid_jpeg(size: tuple[int, int] = (1024, 1024)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(128, 128, 128)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


_VALID_JPEG = _valid_jpeg()


def _register_user(client, telegram_id: int = 999001) -> str:
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
def test_create_analysis_returns_202(mock_get_storage, mock_get_arq, client):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage

    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999002)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers=_auth(token),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert "task_id" in body
    pool.enqueue_job.assert_awaited()


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_get_task_after_create(mock_get_storage, mock_get_arq, client):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    tid = 999003
    token = _register_user(client, telegram_id=tid)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "dating"},
        headers=_auth(token),
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    r2 = client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["task_id"] == task_id
    assert data["status"] == "pending"
    assert data["mode"] == "dating"


def test_analyze_without_consent_returns_451(client):
    token = _register_user(client, telegram_id=999004)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 451, r.text
    detail = r.json().get("detail", {})
    assert detail.get("code") == "consent_required"
    missing = detail.get("missing") or []
    assert "data_processing" in missing
    assert "ai_transfer" in missing
