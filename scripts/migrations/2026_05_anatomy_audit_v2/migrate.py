"""v1.77 anatomy audit v2 — lint holes + P0 style hotfixes.

Closes gaps found in the May 2026 catalogue audit:

* ``EXPRESSION_PORTRAIT_LEAK`` missed ``authority``, ``intense gaze``,
  ``still brow``, ``shoulders visible in frame``.
* ``WARDROBE_POSE_LEAK`` missed ``collar and shoulder seam clearly
  visible`` / ``crew-neck shoulder line clearly visible``.
* ``TIGHT_INDOOR_SCREEN_SCENE`` did not scan lighting pools — ring
  light / monitor glow / leather chair still reached the wire prompt.
* ``mirror_aesthetic`` trigger_pool still carried ``mirror selfie``.
* ``panoramic_window`` scene still asked for ``face clearly lit from
  front, dramatic scale``.

Usage::

    python scripts/migrations/2026_05_anatomy_audit_v2/migrate.py --dry-run
    python scripts/migrations/2026_05_anatomy_audit_v2/migrate.py
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LOG_PATH = Path(__file__).resolve().parent / "MIGRATION_LOG.md"

_STUDIO_EXEMPT = frozenset({"formal_portrait", "studio_elegant"})
_DOCUMENT_EXEMPT = frozenset(
    {
        "photo_3x4",
        "passport_rf",
        "visa_eu",
        "visa_schengen",
        "visa_us",
        "photo_4x6",
        "driver_license",
    }
)
_EXEMPT = _STUDIO_EXEMPT | _DOCUMENT_EXEMPT

# Drop lighting / override lines that encode webcam-tight crops.
_LIGHTING_DROP_RE = re.compile(
    r"\b("
    r"ring[\s-]*light"
    r"|monitor\s+glow"
    r"|on\s+screen"
    r"|webcam"
    r"|leather\s+chair"
    r"|behind\s+(?:a|the)\s+desk"
    r"|mirror\s+selfie"
    r")\b",
    re.IGNORECASE,
)

_WARDROBE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "collar and shoulder seam clearly visible",
        "well-fitted across the shoulders",
    ),
    (
        "crew-neck shoulder line clearly visible",
        "well-fitted across the shoulders",
    ),
    (
        ", shoulders fully in frame",
        ", well-fitted across the shoulders",
    ),
)

_AUTHORITY_TAIL_RE = re.compile(
    r",?\s*(?:calm|intelligent|medical|artistic|technical|timeless|"
    r"approachable|calm\s+technical)?\s*authority\.?",
    re.IGNORECASE,
)

_SHOULDERS_VISIBLE_RE = re.compile(
    r",?\s*shoulders\s+visible\s+in\s+frame\.?",
    re.IGNORECASE,
)

_STILL_BROW_RE = re.compile(
    r",?\s*(?:productive|modern|evening)\s+still\s+brow\.?",
    re.IGNORECASE,
)

_COMPOSED_GAZE_RE = re.compile(
    r"\bComposed\s+(?:confident|direct|steady|decisive|analytical)\s+gaze\b",
    re.IGNORECASE,
)

_EYE_CONTACT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("warm inviting eye contact", "warm inviting smile"),
    ("direct steady eye contact, alluring gaze", "relaxed half-smile, steady gaze"),
    ("engaged eye contact, soulful gaze", "engaged expression, soulful gaze"),
    ("engaged eye contact, relaxed romantic gaze", "warm smile, relaxed romantic gaze"),
    ("Engaging direct eye contact, animated charismatic expression", "Engaging animated expression, confident smile"),
)

_P0_PATCHES: dict[str, dict[str, Any]] = {
    "mirror_aesthetic": {
        "trigger_pool_replace": {
            "mirror selfie composition with the reflection visible": (
                "modern interior with mirror as a focal accent, reflection visible"
            ),
        },
    },
    "panoramic_window": {
        "base_scene": (
            "standing before massive floor-to-ceiling window with dramatic "
            "city panorama, soft rim light from the window, balanced natural light"
        ),
        "scene_anchor": (
            "standing before massive floor-to-ceiling window with dramatic "
            "city panorama, soft rim light from the window, balanced natural light"
        ),
        "default_clothing": (
            "minimal dark outfit against bright cityscape, well-fitted across "
            "the shoulders"
        ),
    },
    "boardroom": {
        "expression": (
            "Confident open expression, relaxed direct gaze, natural brow."
        ),
    },
    "legal_finance": {
        "expression": (
            "Confident relaxed expression, settled direct gaze, natural mouth line."
        ),
    },
    "video_call": {
        "expression": (
            "Engaged expression, warm professional smile, open attentive eyes."
        ),
    },
    "analytics_review": {
        "expression": (
            "Sharp analytical expression, slight concentration furrow, "
            "focused professional eyes."
        ),
    },
    "tech_developer": {
        "expression": (
            "Alert focused expression, confident technical gaze, calm brow."
        ),
    },
    "creative_director": {
        "expression": (
            "Intense creative gaze, visionary confident expression, "
            "focused artistic eyes."
        ),
    },
    "medical": {
        "expression": (
            "Warm empathetic expression, trustworthy caring gaze, "
            "calm professional eyes."
        ),
    },
    "podcast": {
        "expression": (
            "Natural animated expression, engaging conversational smile, "
            "approachable presence."
        ),
    },
    "construction_foreman": {
        "expression": (
            "Composed confident gaze, steady professional smile."
        ),
    },
    "welder_industrial": {
        "expression": (
            "Focused attentive gaze, steady professional smile, calm artisan eyes."
        ),
    },
}


def _patch_string(value: str) -> tuple[str, bool]:
    if not isinstance(value, str) or not value.strip():
        return value, False
    original = value
    for old, new in _WARDROBE_REPLACEMENTS:
        if old in value:
            value = value.replace(old, new)
    for old, new in _EYE_CONTACT_REPLACEMENTS:
        if old in value:
            value = value.replace(old, new)
    value = _AUTHORITY_TAIL_RE.sub("", value)
    value = _SHOULDERS_VISIBLE_RE.sub("", value)
    value = _STILL_BROW_RE.sub("", value)
    value = _COMPOSED_GAZE_RE.sub("Confident steady gaze", value)
    value = re.sub(r"\s{2,}", " ", value).strip()
    if value and value[-1] not in ".!?":
        value = value + "."
    return value, value != original


def _scrub_pool(items: list[str]) -> tuple[list[str], int]:
    if not items:
        return items, 0
    out: list[str] = []
    dropped = 0
    for item in items:
        if not isinstance(item, str):
            continue
        if _LIGHTING_DROP_RE.search(item):
            dropped += 1
            continue
        patched, _ = _patch_string(item)
        out.append(patched)
    return out, dropped


def _apply_p0(style: dict[str, Any], patch: dict[str, Any]) -> int:
    changes = 0
    sid = style.get("id", "")
    for key in ("base_scene", "scene_anchor", "expression", "default_clothing"):
        if key in patch:
            if style.get(key) != patch[key]:
                style[key] = patch[key]
                changes += 1
    if "trigger_pool_replace" in patch:
        pool = style.get("trigger_pool")
        if isinstance(pool, list):
            new_pool = []
            for item in pool:
                if not isinstance(item, str):
                    new_pool.append(item)
                    continue
                replaced = item
                for old, new in patch["trigger_pool_replace"].items():
                    if old in replaced:
                        replaced = replaced.replace(old, new)
                        changes += 1
                new_pool.append(replaced)
            style["trigger_pool"] = new_pool
    bg = style.get("background")
    if isinstance(bg, dict) and "base_scene" in patch:
        if bg.get("base") != patch["base_scene"]:
            bg["base"] = patch["base_scene"]
            changes += 1
    return changes


def _walk_clothing(style: dict[str, Any]) -> int:
    changes = 0
    for key in ("default_clothing",):
        val = style.get(key)
        if isinstance(val, str):
            new_val, ch = _patch_string(val)
            if ch:
                style[key] = new_val
                changes += 1
    block = style.get("clothing")
    if isinstance(block, dict):
        default = block.get("default")
        if isinstance(default, dict):
            for gk in ("male", "female", "neutral"):
                val = default.get(gk)
                if isinstance(val, str):
                    new_val, ch = _patch_string(val)
                    if ch:
                        default[gk] = new_val
                        changes += 1
    return changes


def _walk_pools(style: dict[str, Any]) -> int:
    changes = 0
    ambient = style.get("ambient")
    if isinstance(ambient, dict) and isinstance(ambient.get("lighting"), list):
        new_pool, dropped = _scrub_pool(ambient["lighting"])
        if dropped:
            ambient["lighting"] = new_pool
            changes += dropped
    for path in ("allowed_variations", "context_slots"):
        block = style.get(path)
        if isinstance(block, dict) and isinstance(block.get("lighting"), list):
            new_pool, dropped = _scrub_pool(block["lighting"])
            if dropped:
                block["lighting"] = new_pool
                changes += dropped
    if isinstance(style.get("scene_overrides"), list):
        new_pool, dropped = _scrub_pool(style["scene_overrides"])
        if dropped:
            style["scene_overrides"] = new_pool
            changes += dropped
    return changes


def migrate_styles(
    styles: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {"styles_touched": 0, "fields_changed": 0, "p0": 0, "p1": 0}
    for style in styles:
        sid = str(style.get("id") or "")
        if sid in _EXEMPT:
            continue
        style_changes = 0
        if sid in _P0_PATCHES:
            style_changes += _apply_p0(style, _P0_PATCHES[sid])
            stats["p0"] += 1
        style_changes += _walk_clothing(style)
        if isinstance(style.get("expression"), str):
            new_expr, ch = _patch_string(style["expression"])
            if ch:
                style["expression"] = new_expr
                style_changes += 1
        style_changes += _walk_pools(style)
        if style_changes:
            stats["styles_touched"] += 1
            stats["fields_changed"] += style_changes
            stats["p1"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with STYLES_PATH.open(encoding="utf-8") as fh:
        styles = json.load(fh)

    stats = migrate_styles(styles, dry_run=args.dry_run)
    print(
        f"anatomy_audit_v2: touched={stats['styles_touched']} "
        f"field_ops={stats['fields_changed']} p0={stats['p0']} dry_run={args.dry_run}"
    )

    if args.dry_run:
        return 0

    fd, tmp = tempfile.mkstemp(suffix=".json", dir=STYLES_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(styles, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, STYLES_PATH)
    except Exception:
        os.unlink(tmp)
        raise

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n## {ts}\n")
        log.write(f"- stats: {stats}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
