"""Normalize stored /api storage URLs to the current public API base."""

from __future__ import annotations

import re

_STORAGE_PATH_RE = re.compile(r"/storage/.+")


def normalize_storage_url(url: str, api_base_url: str) -> str:
    """Rewrite any storage URL to use ``api_base_url`` (public HTTPS).

    Handles URLs stored in DB with an outdated base (e.g. old deploy host).
    """
    if not url:
        return ""
    m = _STORAGE_PATH_RE.search(url)
    if m:
        base = (api_base_url or "").rstrip("/")
        return f"{base}{m.group(0)}"
    if url.startswith("http"):
        return url
    base = (api_base_url or "").rstrip("/")
    return f"{base}/storage/{url.lstrip('/')}"
