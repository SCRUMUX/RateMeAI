"""Verify the bot maps the worker's structured ``error_message`` to the
user-friendly Russian explanation (C fix).

The worker writes strings like ``[stage=analyze] ReadTimeout: ...`` and the
bot must not show that raw text to the user — it should translate it into
an actionable hint. Keep this test in sync with
``web/src/lib/task-error.ts::userMessageForFailed``.
"""
from __future__ import annotations

import pytest

from src.bot.handlers.mode_select import (
    _GENERIC_FAILED_MESSAGE,
    _user_message_for_failed,
)


@pytest.mark.parametrize("msg", [
    "[stage=preprocess] ValueError: На фото не обнаружено лицо. Загрузите портрет...",
    "[stage=preprocess] ValueError: no_face",
    "[stage=preprocess] ValueError: face_too_small",
    "[stage=preprocess] ValueError: Фото слишком размыто",
])
def test_preprocess_no_face_variants(msg):
    out = _user_message_for_failed(msg)
    assert "фронтальный портрет" in out.lower() or "чётк" in out.lower()
    assert out != _GENERIC_FAILED_MESSAGE


@pytest.mark.parametrize("msg", [
    "[stage=analyze] ReadTimeout: 30s exceeded",
    "[stage=analyze] TimeoutError: read timed out",
    "[stage=analyze] HTTPStatusError: 503 Service Unavailable",
    "[stage=analyze] HTTPStatusError: 429 Too Many Requests",
    "[stage=generate_image] RuntimeError: rate limit exceeded",
])
def test_transient_overload_variants(msg):
    out = _user_message_for_failed(msg)
    assert "перегруж" in out.lower() or "через минуту" in out.lower()
    assert out != _GENERIC_FAILED_MESSAGE


def test_content_policy_violation():
    out = _user_message_for_failed(
        "[stage=generate_image] RuntimeError: Reve: content policy violation"
    )
    assert "безопасн" in out.lower()


def test_ai_transfer_forbidden():
    out = _user_message_for_failed(
        "[stage=analyze] AITransferForbiddenError: no_pipeline_context"
    )
    # no_pipeline_context is matched first in the order → internal error bucket.
    assert "внутренн" in out.lower() or "16+" in out


def test_empty_or_none_returns_generic():
    assert _user_message_for_failed("") == _GENERIC_FAILED_MESSAGE
    assert _user_message_for_failed(None) == _GENERIC_FAILED_MESSAGE  # type: ignore[arg-type]


def test_unknown_error_returns_generic():
    out = _user_message_for_failed("[stage=finalize] KeyError: 'result'")
    assert out == _GENERIC_FAILED_MESSAGE
