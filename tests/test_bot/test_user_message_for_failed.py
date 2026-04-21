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
    "[stage=preprocess] ValueError: face_blurred",
    "[stage=preprocess] ValueError: Фото слишком размыто",
    "[stage=preprocess] ValueError: Лицо на фото размыто. Переснимите в фокусе",
])
def test_preprocess_no_face_variants(msg):
    out = _user_message_for_failed(msg)
    assert "фронтальный портрет" in out.lower() or "чётк" in out.lower()
    assert out != _GENERIC_FAILED_MESSAGE


@pytest.mark.parametrize("msg", [
    "[stage=preprocess] ValueError: На фото несколько человек. Загрузите портрет одного человека.",
    "[stage=preprocess] ValueError: multiple_faces",
])
def test_preprocess_multiple_faces(msg):
    out = _user_message_for_failed(msg)
    assert "одного человека" in out.lower()
    assert out != _GENERIC_FAILED_MESSAGE


@pytest.mark.parametrize("msg", [
    "[stage=preprocess] ValueError: Invalid image file: cannot identify image",
    "[stage=preprocess] ValueError: Unsupported format: HEIF",
    "[stage=preprocess] ValueError: Image too small: 200x300. Minimum 100x100.",
    "[stage=preprocess] ValueError: Не удалось открыть изображение. Загрузите JPG или PNG.",
    "[stage=preprocess] ValueError: invalid_image",
])
def test_preprocess_invalid_image(msg):
    out = _user_message_for_failed(msg)
    assert "jpg или png" in out.lower() or "изображение" in out.lower()
    assert out != _GENERIC_FAILED_MESSAGE


@pytest.mark.parametrize("msg", [
    "[stage=worker] RuntimeError: Task input stash expired and no legacy storage key is available (privacy retention policy). Task must be re-submitted by the user.",
    "[stage=worker] RuntimeError: stash expired",
])
def test_stash_expired(msg):
    out = _user_message_for_failed(msg)
    assert "истекло" in out.lower() or "загрузи фото ещё раз" in out.lower()
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


def test_moderation_russian():
    out = _user_message_for_failed(
        "[stage=analyze] ValueError: Фото не прошло модерацию: adult_content"
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


def test_unknown_english_returns_generic():
    """Unknown English message without Cyrillic tail falls back to generic."""
    out = _user_message_for_failed("[stage=finalize] KeyError: 'result'")
    assert out == _GENERIC_FAILED_MESSAGE


def test_unknown_russian_tail_surfaces_to_user():
    """For unknown patterns, if the tail is readable Russian, we surface it.

    This is the diagnostic fallback: the worker may produce new ValueError
    messages in Russian (e.g. from custom gates) — instead of hiding them
    behind a generic message, we show them so the user knows what to do.
    """
    out = _user_message_for_failed(
        "[stage=preprocess] ValueError: Новый неизвестный блокер. Перезагрузите фото в другом формате."
    )
    assert "не удалось сгенерировать фото:" in out.lower()
    assert "новый неизвестный блокер" in out.lower()
    assert out != _GENERIC_FAILED_MESSAGE


def test_unknown_russian_tail_truncated():
    """Very long tail is capped to avoid Telegram message-length issues."""
    long_tail = "Очень длинное сообщение об ошибке " * 40
    out = _user_message_for_failed(
        f"[stage=finalize] ValueError: {long_tail}"
    )
    assert len(out) < 400
    assert "..." in out
