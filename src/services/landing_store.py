"""Atomic writer for ``data/landing_content.json`` + hot-reload cache.

We mirror the admin styles pattern (see :mod:`src.services.style_store`):
- JSON on disk is the source of truth (no DB migration).
- Writes are atomic (tmp + os.replace) under a process lock.
- Read path is cached in-memory but can be invalidated after saves.

Per-market content (Variant B / 1.57.0)
---------------------------------------

The CMS-hub model puts the editor (Railway) in charge of every market —
both ``landing_content.json`` (RU) and ``landing_content.global.json``
live side-by-side on the same disk and the admin panel chooses which
one to serve via an explicit ``market`` argument. The RU edge follower
keeps a slimmed-down copy of ``landing_content.json`` only and never
writes through the admin API — its only writes come from the signed
``POST /internal/cms/replicate`` receiver and the hourly safety-pull
cron.

Resolution rules:
- ``ru`` → ``data/landing_content.json`` (legacy filename, kept as the
  RU source of truth so RU edge can roll out without touching disk).
- everything else (``global``, ``th``, …) → ``data/landing_content.<market>.json``
  with a fallback to ``data/landing_content.global.json`` and finally
  to an empty ``{"pages": {}}`` document. The frontend already falls
  back to the i18n bundle when CMS fields are blank, so an empty
  payload renders English copy on the global build without code
  changes.

Public API:
- ``load_landing_content(market=None)`` — read for the active or
  explicit market (cached per market).
- ``save_landing_content(payload, market=None)`` — atomic write +
  cache invalidation for the targeted market.
- ``available_markets()`` — list of markets the editor can edit (used
  by the admin UI to populate the market switcher).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
LANDING_PATH = DATA_DIR / "landing_content.json"

# Markets the editor exposes in the admin UI. ``ru`` keeps the legacy
# filename; every other entry maps to ``landing_content.<market>.json``
# under the same directory. Adding a new market here is a one-line
# change and does not require any disk migration — the loader simply
# returns ``{"pages": {}}`` until the first save.
KNOWN_MARKETS: tuple[str, ...] = ("ru", "global")
DEFAULT_MARKET = "global"

_WRITE_LOCK = threading.Lock()
_CACHE: dict[str, dict[str, Any]] = {}


def _normalize_market(market: str | None) -> str:
    value = (market or "").strip().lower()
    if value in KNOWN_MARKETS:
        return value
    if value == "":
        return _active_market()
    # Unknown market — fall back to the global file. We intentionally do
    # not raise so a misconfigured caller still gets a deterministic
    # (empty) document instead of an HTTP 500.
    return DEFAULT_MARKET


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _active_market() -> str:
    """Resolve the live market id without importing settings at module
    load (the singleton is built lazily to keep tests cheap)."""
    try:
        from src.config import settings  # local import: avoid circular deps
    except Exception:
        return DEFAULT_MARKET
    try:
        value = (settings.resolved_market_id or DEFAULT_MARKET).strip().lower()
        return value or DEFAULT_MARKET
    except Exception:
        return DEFAULT_MARKET


def _resolve_landing_path(market: str | None = None) -> Path:
    """Pick the on-disk JSON file for ``market``.

    The lookup is scoped to ``LANDING_PATH.parent`` so unit tests can
    redirect the whole stack with a single ``monkeypatch.setattr`` on
    ``LANDING_PATH`` (the per-market siblings inherit the override).
    """
    base_dir = LANDING_PATH.parent
    resolved = _normalize_market(market)
    if resolved == "ru":
        return LANDING_PATH
    candidate = base_dir / f"landing_content.{resolved}.json"
    if candidate.exists():
        return candidate
    fallback_global = base_dir / "landing_content.global.json"
    if fallback_global.exists():
        return fallback_global
    return LANDING_PATH


def invalidate_cache(market: str | None = None) -> None:
    """Drop cached document for ``market`` (or all markets if None)."""
    global _CACHE
    if market is None:
        _CACHE.clear()
        return
    resolved = _normalize_market(market)
    _CACHE.pop(resolved, None)


def load_landing_content(market: str | None = None) -> dict[str, Any]:
    """Load landing content for ``market`` from disk, using in-memory cache."""
    resolved = _normalize_market(market)
    cached = _CACHE.get(resolved)
    if cached is not None:
        return cached
    path = _resolve_landing_path(resolved)
    if not path.exists():
        data: dict[str, Any] = {"pages": {}}
    else:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {"pages": {}}
    if not isinstance(data, dict):
        data = {"pages": {}}
    if "pages" not in data or not isinstance(data.get("pages"), dict):
        data["pages"] = {}
    _CACHE[resolved] = data
    return data


def load_landing_content_fresh(market: str | None = None) -> dict[str, Any]:
    """Bypass cache and return on-disk truth (used by admin list/get)."""
    invalidate_cache(market)
    return load_landing_content(market)


def save_landing_content(
    payload: dict[str, Any],
    market: str | None = None,
) -> None:
    if not isinstance(payload, dict):
        raise TypeError(f"landing content must be a dict, got {type(payload).__name__}")
    resolved = _normalize_market(market)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    target = _resolve_landing_path(resolved)
    with _WRITE_LOCK:
        _atomic_write(target, text)
        invalidate_cache(resolved)


def content_hash(payload: dict[str, Any]) -> str:
    """Stable hash of a CMS document — used to short-circuit replication
    when the editor's snapshot already matches the follower copy."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def available_markets() -> tuple[str, ...]:
    """Markets the editor admin UI can switch between."""
    return KNOWN_MARKETS
