"""Tests for the legacy A/B form fields on POST /api/v1/analyze.

Post Nano-Banana cleanup ``image_model`` is always normalised to
``gpt_image_2`` regardless of what the client posts; the tests pin
that contract plus the feature-flag gate (``ab_test_enabled``). Uses
the same integration-style ``client`` fixture as :mod:`test_analyze`;
skipped automatically when Postgres/Redis aren't reachable.

We capture the task context by wrapping :class:`src.models.task.Task`'s
constructor so we can inspect the ``context`` kwarg the endpoint
assembles without touching the ORM session.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from src.config import settings

_CONSENT_HEADERS = {
    "X-Consent-Data-Processing": "1",
    "X-Consent-AI-Transfer": "1",
    "X-Consent-Age-16": "1",
}


def _valid_jpeg(size: tuple[int, int] = (1024, 1024)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(128, 128, 128)).save(
        buf,
        format="JPEG",
        quality=90,
    )
    return buf.getvalue()


_VALID_JPEG = _valid_jpeg()


def _register_user(client, telegram_id: int) -> str:
    r = client.post(
        "/api/v1/auth/telegram",
        json={
            "telegram_id": telegram_id,
            "username": "ab_tester",
            "first_name": "Test",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **_CONSENT_HEADERS}


class _TaskCtxCapture:
    """Context manager that wraps ``Task.__init__`` and records every
    ``context`` kwarg it receives during the test. The original behavior
    is preserved so the endpoint can still persist the row normally."""

    def __init__(self):
        self.contexts: list[dict] = []
        self._patcher = None
        self._orig_init = None

    def __enter__(self):
        from src.models.db import Task

        self._orig_init = Task.__init__
        capture = self

        def _wrapped(self, *args, **kwargs):
            capture.contexts.append(kwargs.get("context") or {})
            return capture._orig_init(self, *args, **kwargs)

        self._patcher = patch.object(Task, "__init__", _wrapped)
        self._patcher.start()
        return self

    def __exit__(self, *exc):
        self._patcher.stop()
        return False


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_pins_image_model_to_gpt_image_2(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    """Even when the client posts a legacy ``image_model=nano_banana_2``
    the endpoint must collapse it to ``gpt_image_2`` — that is the
    single live image model in the pipeline."""
    monkeypatch.setattr(settings, "ab_test_enabled", True)
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999101)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={
                "mode": "rating",
                "image_model": "nano_banana_2",
                "image_quality": "high",
            },
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    assert cap.contexts, "Task() was not instantiated during create_analysis"
    ctx = cap.contexts[-1]
    assert ctx.get("image_model") == "gpt_image_2"
    # quality is locked to the production-optimal "medium" on the
    # server regardless of what the client submits.
    assert ctx.get("image_quality") == "medium"


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_unknown_model_resolves_to_gpt_image_2(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    """Unknown / garbage ``image_model`` values also resolve to the
    single live model."""
    monkeypatch.setattr(settings, "ab_test_enabled", True)
    monkeypatch.setattr(settings, "ab_default_model", "gpt_image_2")
    monkeypatch.setattr(settings, "ab_default_quality", "medium")
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999102)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={
                "mode": "rating",
                "image_model": "flux_42",
                "image_quality": "high",
            },
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    ctx = cap.contexts[-1]
    assert ctx.get("image_model") == "gpt_image_2"
    # quality is always normalised to "medium" server-side, even
    # when the client submitted a valid non-medium tier.
    assert ctx.get("image_quality") == "medium"


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_unknown_quality_falls_back_to_default(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ab_test_enabled", True)
    monkeypatch.setattr(settings, "ab_default_quality", "medium")
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999103)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={
                "mode": "rating",
                "image_model": "gpt_image_2",
                "image_quality": "ultra",
            },
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    ctx = cap.contexts[-1]
    assert ctx.get("image_model") == "gpt_image_2"
    assert ctx.get("image_quality") == "medium"


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_ignores_ab_fields_when_feature_flag_off(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ab_test_enabled", False)
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999104)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={
                "mode": "rating",
                "image_model": "gpt_image_2",
                "image_quality": "high",
            },
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    ctx = cap.contexts[-1]
    assert "image_model" not in ctx
    assert "image_quality" not in ctx


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_persists_framing_and_input_hints(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    """v1.26: ``framing`` (токбл ракурса на 3-м шаге) и ``input_hints``
    (поля модалки «Другой вариант») доходят до Task.context и позже
    читаются пайплайном. Здесь проверяем только персист — дальнейший
    роутинг до PromptEngine покрыт модульными тестами executor'a."""
    import json as _json

    monkeypatch.setattr(settings, "ab_test_enabled", True)
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    hints = {"lighting": "golden hour", "clothing_override": "white linen shirt"}
    token = _register_user(client, telegram_id=999106)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={
                "mode": "rating",
                "image_model": "gpt_image_2",
                "image_quality": "medium",
                "framing": "half_body",
                "input_hints": _json.dumps(hints),
            },
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    ctx = cap.contexts[-1]
    assert ctx.get("framing") == "half_body"
    assert ctx.get("input_hints") == hints


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_ignores_invalid_input_hints_json(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    """Битый JSON в ``input_hints`` не должен ронять запрос — поле
    просто не попадает в context (см. логирование в analyze.py)."""
    monkeypatch.setattr(settings, "ab_test_enabled", True)
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999107)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={
                "mode": "rating",
                "framing": "portrait",
                "input_hints": "{not-json",
            },
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    ctx = cap.contexts[-1]
    assert ctx.get("framing") == "portrait"
    assert "input_hints" not in ctx


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_analyze_without_ab_fields_defaults_to_gpt_image_2_medium(
    mock_get_storage,
    mock_get_arq,
    client,
    monkeypatch,
):
    """When the client omits both fields (old bot / curl), the
    endpoint still pins ``image_model=gpt_image_2`` +
    ``image_quality=medium`` because that is the single live
    configuration in the pipeline."""
    monkeypatch.setattr(settings, "ab_test_enabled", True)
    monkeypatch.setattr(settings, "ab_default_model", "gpt_image_2")
    monkeypatch.setattr(settings, "ab_default_quality", "medium")
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999105)
    with _TaskCtxCapture() as cap:
        r = client.post(
            "/api/v1/analyze",
            files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
            data={"mode": "rating"},
            headers=_auth(token),
        )
    assert r.status_code == 202, r.text
    ctx = cap.contexts[-1]
    assert ctx.get("image_model") == "gpt_image_2"
    assert ctx.get("image_quality") == "medium"
