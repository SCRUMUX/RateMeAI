"""Unit tests for the PII-stripping logging filter.

The filter is the last line of defence before stdout/CloudWatch — if
anything PII-shaped (email, phone, telegram_id) reaches a log record's
``msg`` / ``args`` / extra fields, the filter must mask it.
"""

from __future__ import annotations

import logging

from src.utils.log_filters import PIIFilter


def _make_record(msg: str, args=None, **extra) -> logging.LogRecord:
    rec = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def _formatted(rec: logging.LogRecord) -> str:
    if rec.args is None:
        return rec.msg
    try:
        return rec.msg % rec.args
    except TypeError:
        # tuple of args
        return rec.msg


def test_filter_masks_emails_in_msg() -> None:
    rec = _make_record("login from user vasya@gmail.com (Google)")
    PIIFilter().filter(rec)
    assert "vasya@gmail.com" not in rec.msg
    assert "[REDACTED_PII]" in rec.msg


def test_filter_masks_phone_in_msg() -> None:
    rec = _make_record("phone: +7 999 123-45-67 verified")
    PIIFilter().filter(rec)
    assert "+7 999 123-45-67" not in rec.msg
    assert "[REDACTED_PII]" in rec.msg


def test_filter_masks_telegram_id_in_msg() -> None:
    rec = _make_record("user telegram_id=987654321 paid for credits")
    PIIFilter().filter(rec)
    assert "987654321" not in rec.msg


def test_filter_masks_pii_keys_in_dict_args() -> None:
    args = {
        "email": "ivan@yandex.ru",
        "telegram_id": 123456789,
        "first_name": "Иван",
        "language_code": "ru",
        "innocent": "ok",
    }
    rec = _make_record("user %s", args=args)
    PIIFilter().filter(rec)
    new_args = rec.args
    assert isinstance(new_args, dict)
    assert new_args["email"] == "[REDACTED_PII]"
    assert new_args["telegram_id"] == "[REDACTED_PII]"
    assert new_args["first_name"] == "[REDACTED_PII]"
    assert new_args["language_code"] == "[REDACTED_PII]"
    # Non-PII keys must pass through untouched.
    assert new_args["innocent"] == "ok"


def test_filter_keeps_uuid_unmasked() -> None:
    rec = _make_record("processing task 12345678-1234-1234-1234-123456789012")
    PIIFilter().filter(rec)
    assert "12345678-1234-1234-1234-123456789012" in rec.msg


def test_filter_keeps_base64_image_masking_behavior() -> None:
    long_b64 = "A" * 250
    rec = _make_record(f"data:image/png;base64,{long_b64}")
    PIIFilter().filter(rec)
    assert long_b64 not in rec.msg
    assert "[REDACTED_IMG]" in rec.msg
