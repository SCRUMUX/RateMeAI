"""Atomic writer for ``data/landing_content.json`` + hot-reload cache.

We mirror the admin styles pattern (see :mod:`src.services.style_store`):
- JSON on disk is the source of truth (no DB migration).
- Writes are atomic (tmp + os.replace) under a process lock.
- Read path is cached in-memory but can be invalidated after saves.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LANDING_PATH = REPO_ROOT / "data" / "landing_content.json"

_WRITE_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None


def load_landing_content() -> dict[str, Any]:
    """Load landing content from disk, using in-memory cache."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not LANDING_PATH.exists():
        _CACHE = {"pages": {}}
        return _CACHE
    raw = LANDING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw) if raw.strip() else {"pages": {}}
    if not isinstance(data, dict):
        data = {"pages": {}}
    if "pages" not in data or not isinstance(data.get("pages"), dict):
        data["pages"] = {}
    _CACHE = data
    return data


def load_landing_content_fresh() -> dict[str, Any]:
    """Bypass cache and return on-disk truth (used by admin list/get)."""
    invalidate_cache()
    return load_landing_content()


def save_landing_content(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise TypeError(f"landing content must be a dict, got {type(payload).__name__}")
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with _WRITE_LOCK:
        _atomic_write(LANDING_PATH, text)
        invalidate_cache()

