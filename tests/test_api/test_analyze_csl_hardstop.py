"""Integration tests for the Composition Safety Layer (CSL) hard-stop
on ``/api/v1/analyze``.

These tests require Postgres + Redis (matching the rest of ``test_api/``).
They verify that the server refuses requests whose ``framing`` is not in
the policy ``allowed_framings`` written by ``/api/v1/pre-analyze`` —
even when the frontend would normally have hidden the option. This is the
defence-in-depth half of the wizard's UI gating: a hand-crafted curl call
must NOT be able to ask FLUX Kontext Pro for a "full_body" output when the
input photo is a tight face-closeup.
"""

from __future__ import annotations

import asyncio
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

_CONSENT_HEADERS = {
    "X-Consent-Data-Processing": "1",
    "X-Consent-AI-Transfer": "1",
    "X-Consent-Age-16": "1",
}


def _valid_jpeg(size: tuple[int, int] = (1024, 1024)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(128, 128, 128)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


_VALID_JPEG = _valid_jpeg()


def _register_user(client, telegram_id: int) -> str:
    r = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": telegram_id, "username": "csl-test", "first_name": "T"},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **_CONSENT_HEADERS}


async def _write_cache(client, pre_analysis_id: str, csl_meta: dict) -> None:
    """Seed Redis with a fake ``preanalysis_cache`` entry so the hard-stop
    finds CSL metadata. Mirrors what ``/api/v1/pre-analyze`` writes."""
    from src.config import settings
    from src.utils.redis_keys import preanalysis_cache_key

    redis = client.app.state.redis
    key = preanalysis_cache_key(pre_analysis_id, settings.resolved_market_id)
    payload = {
        "first_impression": "stub",
        "score": 7.5,
        "_csl": csl_meta,
    }
    await redis.set(key, json.dumps(payload), ex=600)


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_blocks_full_body_for_face_closeup_input(
    mock_get_storage, mock_get_arq, client
):
    """Hard-stop: ``framing=full_body`` on a face-closeup pre-analysis
    must return HTTP 400 with ``framing_not_allowed`` even though the
    request payload is otherwise valid."""
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999801)

    pre_id = "csl-pre-1"
    asyncio.run(
        _write_cache(
            client,
            pre_id,
            {
                "composition_class": "face_closeup",
                "allowed_framings": ["portrait"],
                "face_area_ratio": 0.45,
            },
        )
    )

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={
            "mode": "dating",
            "pre_analysis_id": pre_id,
            "framing": "full_body",
        },
        headers=_auth(token),
    )

    assert r.status_code == 400, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "framing_not_allowed"
    assert detail.get("composition_class") == "face_closeup"
    assert "portrait" in (detail.get("allowed_framings") or [])
    # The worker must NOT have been enqueued.
    pool.enqueue_job.assert_not_awaited()


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_allows_portrait_on_face_closeup_input(
    mock_get_storage, mock_get_arq, client
):
    """Sanity: a face-closeup input must still accept ``framing=portrait``."""
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999802)
    pre_id = "csl-pre-2"

    asyncio.run(
        _write_cache(
            client,
            pre_id,
            {
                "composition_class": "face_closeup",
                "allowed_framings": ["portrait"],
                "face_area_ratio": 0.45,
            },
        )
    )

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={
            "mode": "dating",
            "pre_analysis_id": pre_id,
            "framing": "portrait",
        },
        headers=_auth(token),
    )

    assert r.status_code == 202, r.text
    pool.enqueue_job.assert_awaited()


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_advanced_override_bypasses_hard_stop(
    mock_get_storage, mock_get_arq, client, monkeypatch
):
    """Phase 3: when ``composition_safety_advanced_override`` is enabled
    AND the client sets ``skip_composition_safety=true``, the hard-stop
    must be skipped and the task must be enqueued."""
    from src.config import settings

    monkeypatch.setattr(settings, "composition_safety_advanced_override", True)

    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999803)
    pre_id = "csl-pre-3"

    asyncio.run(
        _write_cache(
            client,
            pre_id,
            {
                "composition_class": "face_closeup",
                "allowed_framings": ["portrait"],
                "face_area_ratio": 0.45,
            },
        )
    )

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={
            "mode": "dating",
            "pre_analysis_id": pre_id,
            "framing": "full_body",
            "skip_composition_safety": "true",
        },
        headers=_auth(token),
    )

    assert r.status_code == 202, r.text
    pool.enqueue_job.assert_awaited()


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_skip_flag_ignored_when_override_disabled(
    mock_get_storage, mock_get_arq, client, monkeypatch
):
    """A client cannot opt itself in to the advanced override if the
    deployment hasn't enabled ``composition_safety_advanced_override``."""
    from src.config import settings

    monkeypatch.setattr(settings, "composition_safety_advanced_override", False)

    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999804)
    pre_id = "csl-pre-4"

    asyncio.run(
        _write_cache(
            client,
            pre_id,
            {
                "composition_class": "face_closeup",
                "allowed_framings": ["portrait"],
                "face_area_ratio": 0.45,
            },
        )
    )

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={
            "mode": "dating",
            "pre_analysis_id": pre_id,
            "framing": "full_body",
            "skip_composition_safety": "true",
        },
        headers=_auth(token),
    )

    assert r.status_code == 400, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "framing_not_allowed"
    pool.enqueue_job.assert_not_awaited()


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_without_pre_analysis_id_does_not_hard_stop(
    mock_get_storage, mock_get_arq, client
):
    """Legacy clients that don't pass ``pre_analysis_id`` (or skip the
    pre-analyze step entirely) should keep working without CSL hard-stop
    — the prompt assembler's ``head_crop_proportion_lock`` is still the
    last line of defence in that path."""
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999805)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "dating", "framing": "full_body"},
        headers=_auth(token),
    )

    # The request may either succeed (202) or fail on some other validation
    # but it must NOT fail with framing_not_allowed.
    if r.status_code == 400:
        detail = r.json().get("detail") or {}
        assert detail.get("code") != "framing_not_allowed", (
            "CSL hard-stop should not fire when pre_analysis_id is absent — "
            "the legacy executor handles framing instead."
        )
    else:
        assert r.status_code == 202, r.text
