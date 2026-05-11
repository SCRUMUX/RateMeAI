"""Privacy-focused logging filters.

Attaches to the root logger so any call site that accidentally tries to
log image bytes / base64 blobs / large PII-looking strings gets redacted
before the record is emitted to stdout.

The two-region architecture (RU edge + Global primary) doubles down on
the importance of clean logs: even though synthetic ``internal_user_id``
prevents joins on Postgres, log files are a parallel channel that can
leak the same identifiers (telegram_id, language_code, email).
"""

from __future__ import annotations

import logging
import re

_BASE64_CHUNK_RE = re.compile(r"[A-Za-z0-9+/=]{200,}")
_DATA_URL_RE = re.compile(
    r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+",
    re.IGNORECASE,
)

# Mask whole emails, even when the surrounding text is otherwise innocent.
# Tight bound on TLD length keeps file paths / URLs from accidentally
# matching.
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}",
)

# Telegram IDs and phone-like number sequences. Telegram numeric IDs are
# 5–13 digit integers; phone numbers we want to catch usually carry a
# leading "+" or are 10+ digits in a row. We keep this conservative on
# purpose — over-aggressive masking breaks task UUIDs in logs.
_PHONE_RE = re.compile(r"\+\d[\d\-\s]{7,}\d")
_TG_ID_RE = re.compile(r"\b(?:telegram[_\s\-]?id|tg[_\s\-]?id)\s*[:=]\s*(\d{5,})", re.I)

_FORBIDDEN_KEYS = frozenset(
    {
        "image_bytes",
        "image_b64",
        "image",
        "file_bytes",
        "raw_bytes",
    }
)

# Keys whose VALUES are PII and must be masked when they appear in a
# logging.LogRecord's ``args`` dict or as keyword fields on the record.
# Note: keys are matched case-insensitively against ``key.lower()``.
_PII_KEYS = frozenset(
    {
        "email",
        "emails",
        "phone",
        "phone_number",
        "telegram_id",
        "tg_id",
        "telegram_username",
        "tg_username",
        "first_name",
        "last_name",
        "full_name",
        "display_name",
        "language_code",
        "user_email",
    }
)

_REDACTED = "[REDACTED_IMG]"
_REDACTED_PII = "[REDACTED_PII]"


def _scrub_str(value: str) -> str:
    value = _DATA_URL_RE.sub(_REDACTED, value)
    value = _BASE64_CHUNK_RE.sub(_REDACTED, value)
    value = _EMAIL_RE.sub(_REDACTED_PII, value)
    value = _PHONE_RE.sub(_REDACTED_PII, value)
    value = _TG_ID_RE.sub(lambda m: m.group(0).replace(m.group(1), _REDACTED_PII), value)
    return value


def _scrub_value(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"[REDACTED_BYTES len={len(bytes(value))}]"
    if isinstance(value, str):
        return _scrub_str(value)
    return value


class PIIFilter(logging.Filter):
    """Redact image bytes / base64 / explicit PII keys from log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = _scrub_str(record.msg)

            if record.args:
                if isinstance(record.args, dict):
                    new_args = {}
                    for k, v in record.args.items():
                        key_lc = str(k).lower()
                        if k in _FORBIDDEN_KEYS:
                            new_args[k] = _REDACTED
                        elif key_lc in _PII_KEYS:
                            new_args[k] = _REDACTED_PII
                        else:
                            new_args[k] = _scrub_value(v)
                    record.args = new_args
                elif isinstance(record.args, tuple):
                    record.args = tuple(_scrub_value(a) for a in record.args)

            for attr in list(record.__dict__.keys()):
                if attr in _FORBIDDEN_KEYS:
                    setattr(record, attr, _REDACTED)
                elif attr.lower() in _PII_KEYS:
                    setattr(record, attr, _REDACTED_PII)
        except Exception:
            # Never break the log pipeline because of a scrub bug.
            return True
        return True
