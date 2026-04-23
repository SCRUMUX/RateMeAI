"""End-to-end privacy invariants for /analyze.

Covers the consent gate, the "no inputs/* storage" rule, and that the
sanitized bytes flow through Redis rather than durable storage.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


_CONSENT_HEADERS = {
    "X-Consent-Data-Processing": "1",
    "X-Consent-AI-Transfer": "1",
    "X-Consent-Age-16": "1",
}


def _valid_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(140, 120, 100)).save(
        buf, format="JPEG", quality=92
    )
    return buf.getvalue()


_VALID_JPEG = _valid_jpeg()


def _register(client, telegram_id: int) -> str:
    r = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": telegram_id, "username": "priv", "first_name": "Priv"},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_does_not_write_inputs_to_storage(
    mock_get_storage, mock_get_arq, client
):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    mock_get_storage.return_value = storage

    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register(client, telegram_id=777001)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers={"Authorization": f"Bearer {token}", **_CONSENT_HEADERS},
    )
    assert r.status_code == 202, r.text

    # No call to storage.upload for inputs/* — the new privacy layer must keep
    # the original image out of durable storage entirely.
    for call in storage.upload.await_args_list:
        key = call.args[0] if call.args else ""
        assert not str(key).startswith("inputs/"), (
            f"privacy regression: analyze wrote to durable storage key={key!r}"
        )


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_task_response_hides_input_urls(mock_get_storage, mock_get_arq, client):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register(client, telegram_id=777002)
    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "dating"},
        headers={"Authorization": f"Bearer {token}", **_CONSENT_HEADERS},
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    r2 = client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    data = r2.json()
    result = data.get("result") or {}
    for k in ("input_image_url", "input_image_path", "original_image_url"):
        assert result.get(k) in (None, ""), f"leaked input key {k}={result.get(k)!r}"


def test_consents_api_returns_state_after_grant(client):
    token = _register(client, telegram_id=777003)
    auth = {"Authorization": f"Bearer {token}"}

    required_set = {"data_processing", "ai_transfer", "age_confirmed_16"}

    r = client.get("/api/v1/users/me/consents", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert set(body["required"]) == required_set
    assert set(body["missing"]) == required_set

    r = client.post(
        "/api/v1/users/me/consents",
        json={"kinds": list(required_set), "source": "web"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["missing"] == []
    assert set(body["granted"].keys()) == required_set


def test_consent_revoke_blocks_future_analyze(client):
    token = _register(client, telegram_id=777004)
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/v1/users/me/consents",
        json={
            "kinds": ["data_processing", "ai_transfer", "age_confirmed_16"],
            "source": "web",
        },
        headers=auth,
    )
    assert r.status_code == 200

    r = client.post(
        "/api/v1/users/me/consents/revoke",
        json={"kinds": ["ai_transfer"]},
        headers=auth,
    )
    assert r.status_code == 200
    assert "ai_transfer" in r.json()["missing"]

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers=auth,
    )
    assert r.status_code == 451, r.text
    assert "ai_transfer" in r.json()["detail"]["missing"]
