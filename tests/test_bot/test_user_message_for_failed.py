"""Regression contract for the bot's pass-through error renderer.

During generation-pipeline recovery the sanitiser was intentionally
removed: ``_user_message_for_failed`` now just forwards the raw
``task.error_message`` (prefixed with a red cross, capped to 500 chars)
so ops see ``[stage=...] ExcType: ... http=... code=... req=rsid-...``
directly in Telegram / web without reading the DB.

Mirrors ``web/src/lib/task-error.ts::userMessageForFailed`` — both layers
behave identically.
"""
from __future__ import annotations

import pytest

from src.bot.handlers.mode_select import (
    _GENERIC_FAILED_MESSAGE,
    _user_message_for_failed,
)


@pytest.mark.parametrize("msg", [
    "[stage=preprocess] ValueError: На фото не обнаружено лицо.",
    "[stage=preprocess] ValueError: no_face",
    "[stage=preprocess] ValueError: face_blurred",
    "[stage=preprocess] ValueError: multiple_faces",
    "[stage=preprocess] ValueError: Invalid image file: cannot identify image",
    "[stage=worker] RuntimeError: Task input stash expired (privacy retention policy).",
    "[stage=analyze] ReadTimeout: 30s exceeded",
    "[stage=analyze] HTTPStatusError: 503 Service Unavailable",
    "[stage=analyze] HTTPStatusError: 429 Too Many Requests",
    "[stage=generate_image] RuntimeError: rate limit exceeded",
    "[stage=analyze] HTTPStatusError: unauthorized http=401 host=openrouter.ai",
    "[stage=generate_image] RuntimeError: Reve API error: http=400 "
    "code=INVALID_PARAMETER_VALUE req=rsid-abc123",
    "[stage=analyze] AITransferForbiddenError: no_pipeline_context",
])
def test_raw_error_message_is_surfaced(msg):
    """Every structured error_message must flow through to the user text."""
    out = _user_message_for_failed(msg)
    assert out != _GENERIC_FAILED_MESSAGE
    assert msg in out


def test_reve_diagnostic_markers_surface_intact():
    """Critical recovery requirement: Reve code/req markers reach the UI."""
    msg = (
        "[stage=generate_image] RuntimeError: Reve API error: http=400 "
        "code=INVALID_PARAMETER_VALUE req=rsid-abcdef123"
    )
    out = _user_message_for_failed(msg)
    assert "code=INVALID_PARAMETER_VALUE" in out
    assert "req=rsid-abcdef123" in out
    assert "http=400" in out


def test_empty_or_none_returns_generic():
    assert _user_message_for_failed("") == _GENERIC_FAILED_MESSAGE
    assert _user_message_for_failed(None) == _GENERIC_FAILED_MESSAGE
    assert _user_message_for_failed("   ") == _GENERIC_FAILED_MESSAGE


def test_very_long_message_is_capped():
    """Telegram message-length safety: anything over 500 chars is truncated."""
    long_tail = "Очень длинное сообщение об ошибке " * 40
    out = _user_message_for_failed(f"[stage=finalize] ValueError: {long_tail}")
    assert len(out) <= 500 + len("\u274c ")
    assert out.endswith("...")
