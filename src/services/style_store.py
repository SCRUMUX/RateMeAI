"""Atomic writer for ``data/styles.json`` + style-cache hot-reload.

Phase 5.2 of the catalog cleanup. The admin panel needs to update the
JSON catalog without restarting the API worker, and concurrent admin
saves must not corrupt the file. This module owns the write side of
that contract:

* :func:`save_styles` — write the full styles list atomically (temp
  file + ``os.replace``) under a process-level lock, then refresh every
  in-memory cache.
* :func:`invalidate_caches` — drop the v1 ``_STYLES_CACHE``, clear the
  v2 ``STYLE_REGISTRY._v2_by_key`` snapshot, and re-run
  ``register_v2_styles_from_json`` so subsequent ``/catalog/*`` calls
  see the fresh data.

Why no FileLock: the admin surface is single-process (Railway runs one
API container at a time and the migration JSON file is on the same
container disk). Cross-process locking would only matter if a future
deploy fanned multiple API workers across shared storage — at that
point we'd promote styles to PostgreSQL anyway (see plan §5.2).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

# Serialise concurrent saves from the same FastAPI process so a burst of
# admin edits can never interleave their write-then-rename steps.
_WRITE_LOCK = threading.Lock()


def _atomic_write(path: Path, payload: str) -> None:
    """Write ``payload`` to ``path`` via a temp file + ``os.replace``.

    ``os.replace`` is atomic on both POSIX and Windows when source and
    destination live on the same filesystem (which they do — the temp
    file sits next to the target). A reader that opens the file
    in-flight either sees the full pre-write contents or the full
    post-write contents, never a half-flushed mix.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def invalidate_caches() -> None:
    """Drop both v1 and v2 in-memory caches and re-register v2 specs.

    Called from :func:`save_styles` after every successful write, and
    exposed standalone so the admin ``POST /styles/reload`` endpoint
    can force a refresh after an out-of-band edit (e.g. someone hand-
    edited ``data/styles.json`` on the box).

    Also drops the bot ``STYLE_CATALOG`` proxy snapshot so the next
    Telegram keyboard render rebuilds from the freshly-written JSON
    (otherwise admin edits would only reach the bot after the next
    process restart).
    """
    from src.services import style_loader

    style_loader._STYLES_CACHE = []  # noqa: SLF001 — module-private cache reset

    try:
        from src.services.style_catalog import STYLE_CATALOG

        STYLE_CATALOG._invalidate()  # noqa: SLF001 — proxy-private snapshot reset
    except Exception as exc:  # noqa: BLE001 — never break the write path
        logger.warning("style_store: bot catalog reset failed: %s", exc)

    try:
        from src.prompts.image_gen import STYLE_REGISTRY
        from src.services.style_loader_v2 import register_v2_styles_from_json

        STYLE_REGISTRY._v2_by_key.clear()  # noqa: SLF001
        registered = register_v2_styles_from_json()
        logger.info(
            "style_store: caches invalidated, %d v2 specs re-registered", registered
        )
    except Exception as exc:  # noqa: BLE001 — never break the write path
        logger.warning("style_store: v2 re-registration failed: %s", exc)


def save_styles(styles: list[dict[str, Any]]) -> None:
    """Persist ``styles`` to ``data/styles.json`` and refresh caches.

    The list is written verbatim in the same human-readable shape as
    the existing file (2-space indent, UTF-8, trailing newline) so a
    diff between admin saves stays reviewable in git.
    """
    if not isinstance(styles, list):
        raise TypeError(f"styles must be a list, got {type(styles).__name__}")

    payload = json.dumps(styles, indent=2, ensure_ascii=False) + "\n"

    with _WRITE_LOCK:
        _atomic_write(STYLES_PATH, payload)
        invalidate_caches()


def load_styles_fresh() -> list[dict[str, Any]]:
    """Read the styles file bypassing the v1 in-memory cache.

    Useful for the admin ``GET /styles`` list endpoint where we always
    want to return the on-disk truth even if a parallel request just
    primed the cache between requests.
    """
    invalidate_caches()
    from src.services.style_loader import load_styles_from_json

    return load_styles_from_json()
