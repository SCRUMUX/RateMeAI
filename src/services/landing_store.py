"""Atomic writer for ``data/landing_content.json`` + hot-reload cache.

We mirror the admin styles pattern (see :mod:`src.services.style_store`):
- JSON on disk is the source of truth (no DB migration).
- Writes are atomic (tmp + os.replace) under a process lock.
- Read path is cached in-memory but can be invalidated after saves.

Per-market content (1.57.0)
---------------------------

Each region ships its own copy of the repo. We previously kept the
RU-flavoured content in ``data/landing_content.json`` and let the EN
build serve the same RU strings, which leaked Russian copy onto the
``ailookstudio.com`` SPA. Now the loader picks a file based on
``settings.resolved_market_id``:

- ``ru`` → ``data/landing_content.json`` (legacy primary file, kept as
  the RU source of truth).
- everything else (``global``, ``th``, …) → ``data/landing_content.<market>.json``
  with a fallback to ``data/landing_content.global.json`` and finally
  to an empty ``{"pages": {}}`` document. The frontend already falls
  back to the i18n bundle when CMS fields are blank, so an empty
  payload renders English copy on the global build without code
  changes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
LANDING_PATH = DATA_DIR / "landing_content.json"

_WRITE_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _market_id() -> str:
    """Resolve the live market id without importing settings at module
    load (the singleton is built lazily to keep tests cheap)."""
    try:
        from src.config import settings  # local import: avoid circular deps
    except Exception:
        return "global"
    try:
        return (settings.resolved_market_id or "global").strip().lower() or "global"
    except Exception:
        return "global"


def _resolve_landing_path() -> Path:
    """Pick the on-disk JSON file for the active market.

    The RU edge keeps using ``landing_content.json`` (legacy filename),
    every other market reads from a market-specific file with a fallback
    to ``landing_content.global.json`` and finally to ``landing_content.json``
    when neither exists.

    The lookup is scoped to ``LANDING_PATH.parent`` so unit tests can
    redirect the whole stack with a single ``monkeypatch.setattr`` on
    ``LANDING_PATH`` (the per-market siblings inherit the override).
    """
    base_dir = LANDING_PATH.parent
    market = _market_id()
    if market == "ru":
        return LANDING_PATH
    candidate = base_dir / f"landing_content.{market}.json"
    if candidate.exists():
        return candidate
    fallback_global = base_dir / "landing_content.global.json"
    if fallback_global.exists():
        return fallback_global
    return LANDING_PATH


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None


def load_landing_content() -> dict[str, Any]:
    """Load landing content from disk, using in-memory cache."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = _resolve_landing_path()
    if not path.exists():
        _CACHE = {"pages": {}}
        return _CACHE
    raw = path.read_text(encoding="utf-8")
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
    target = _resolve_landing_path()
    with _WRITE_LOCK:
        _atomic_write(target, text)
        invalidate_cache()

