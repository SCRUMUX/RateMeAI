"""Privacy-focused logging filters.

Attaches to the root logger so any call site that accidentally tries to
log image bytes / base64 blobs / large PII-looking strings gets redacted
before the record is emitted to stdout.
"""

from __future__ import annotations

import logging
import re

_BASE64_CHUNK_RE = re.compile(r"[A-Za-z0-9+/=]{200,}")
_DATA_URL_RE = re.compile(
    r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+",
    re.IGNORECASE,
)

_FORBIDDEN_KEYS = frozenset(
    {
        "image_bytes",
        "image_b64",
        "image",
        "file_bytes",
        "raw_bytes",
    }
)

_REDACTED = "[REDACTED_IMG]"


def _scrub_str(value: str) -> str:
    value = _DATA_URL_RE.sub(_REDACTED, value)
    value = _BASE64_CHUNK_RE.sub(_REDACTED, value)
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
                    record.args = {
                        k: _REDACTED if k in _FORBIDDEN_KEYS else _scrub_value(v)
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(_scrub_value(a) for a in record.args)

            for attr in list(record.__dict__.keys()):
                if attr in _FORBIDDEN_KEYS:
                    setattr(record, attr, _REDACTED)
        except Exception:
            # Never break the log pipeline because of a scrub bug.
            return True
        return True
