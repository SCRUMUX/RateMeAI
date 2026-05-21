"""Pin-test: P0 styles must not carry v1.77 forbidden anatomy tokens."""

from __future__ import annotations

import re

from src.services.style_loader import load_styles_from_json

_FORBIDDEN = (
    re.compile(r"mirror\s+selfie", re.I),
    re.compile(r"face\s+clearly\s+lit\s+from\s+front", re.I),
    re.compile(r"dramatic\s+scale", re.I),
    re.compile(r"ring[\s-]*light", re.I),
    re.compile(r"shoulders\s+visible\s+in\s+frame", re.I),
    re.compile(r"collar\s+and\s+shoulder\s+seam\s+clearly\s+visible", re.I),
)

_P0_IDS = frozenset(
    {
        "mirror_aesthetic",
        "panoramic_window",
        "video_call",
        "youtube_creator",
        "analytics_review",
        "tech_developer",
        "legal_finance",
        "boardroom",
    }
)


def _style_text_blob(style: dict) -> str:
    parts: list[str] = []
    for key in (
        "base_scene",
        "scene_anchor",
        "expression",
        "default_clothing",
    ):
        val = style.get(key)
        if isinstance(val, str):
            parts.append(val)
    for pool_key in ("trigger_pool", "scene_overrides"):
        pool = style.get(pool_key)
        if isinstance(pool, list):
            parts.extend(str(x) for x in pool if isinstance(x, str))
    ambient = style.get("ambient")
    if isinstance(ambient, dict):
        lighting = ambient.get("lighting")
        if isinstance(lighting, list):
            parts.extend(str(x) for x in lighting if isinstance(x, str))
    return " ".join(parts)


def test_p0_styles_clean_after_anatomy_audit_v2_migration():
    by_id = {s["id"]: s for s in load_styles_from_json()}
    for sid in sorted(_P0_IDS):
        style = by_id[sid]
        blob = _style_text_blob(style)
        for pat in _FORBIDDEN:
            assert pat.search(blob) is None, (
                f"{sid} still matches {pat.pattern!r} in {blob[:120]!r}..."
            )
