"""v1.71 — indoor-depth normalisation for the CV / studio cohort.

Background
----------

The v1.71 anatomy fix (catalogue v6 strong-shoulders + landmark
scene expansion) closed the "glued head" pathology on outdoor
landmark dating styles. A follow-up production audit showed it is
NOT fully closed on CV / studio styles whose ``scene_anchor``
encodes a *screen-facing tight-crop* semantics — edit-models
trained on the public web associate cues like ``ring light``,
``monitor glow on the subject``, ``webcam``, ``camera on tripod``
and ``headphones on desk`` with front-camera close-up frames and
render the head:body ratio of a webcam selfie regardless of the
requested framing or shoulder paint.

The canonical victim is ``video_call``:

* ``scene_anchor``: ``"clean home office interior, ring light or
  monitor glow on the subject, neat bookshelves visible behind"``
  — every clause is a close-up cue (``on the subject``, close
  back-wall ``visible behind``, ``ring light`` semantics).
* ``default_clothing`` (+ ``clothing.default.*``): ``"... clean
  grooming visible above desk ..."`` — an explicit pose directive
  ("crop the body at desk level") inside the wardrobe channel,
  which is supposed to describe garments only. No shoulder cue
  can override a position directive that ships in the same
  sentence.

Compare with ``dubai_burj_khalifa`` (post v6/landmark fix) which
ships a depth-rich anchor (``boulevard ... rising behind ...
polished marble walkway``) and a wardrobe that names ``tailored
trousers`` — the model has every cue it needs to render a
full-body in proportion.

This migration generalises the depth-rich shape to the CV /
studio cohort:

* **P0 (one style)**: ``video_call`` wardrobe is stripped of the
  ``visible above desk`` leak and re-paired with the strong SUIT-
  grade shoulder cue; expression loses the ``confident screen
  presence`` cue (face-toward-camera directive that bleeds into
  wire prompts when ``use_reference_expression_default=False``).
* **P1 (5 styles)**: ``analytics_review``, ``tech_developer``,
  ``podcast``, ``podcast_host``, ``youtube_creator`` get
  fully-rewritten ``scene_anchor`` + 3 ``scene_overrides`` with
  explicit foreground prop, room-depth backdrop and ambient
  daylight / key-from-side.
* **P2 (5 styles)**: ``standing_desk``, ``online_learning``,
  ``notebook_ideas``, ``tablet_stylus``, ``late_hustle`` get
  smaller surgical edits — add a foreground floor cue + a room-
  depth backdrop cue so the model receives full-frame perspective.

Idempotent: any field already at the new value is left alone; a
re-run reports ``applied=0``.

Usage::

    python scripts/migrations/2026_05_styles_v7_indoor_depth/migrate.py --dry-run
    python scripts/migrations/2026_05_styles_v7_indoor_depth/migrate.py
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LOG_PATH = Path(__file__).resolve().parent / "MIGRATION_LOG.md"


# ---------------------------------------------------------------------------
# P0 — video_call hot fix
# ---------------------------------------------------------------------------
# A single point fix: the wardrobe carries a pose directive that
# overrides every other framing/shoulder cue downstream. The scene
# anchor itself is also rewritten to remove the ``ring light ... on
# the subject`` close-up cue.

VIDEO_CALL_WARDROBE = (
    "professional fitted dress shirt, crisp collar, neat grooming, "
    "well-fitted across the shoulders"
)
VIDEO_CALL_EXPRESSION = (
    "Engaged expression, warm professional smile, "
    "composed confident gaze."
)
VIDEO_CALL_BASE_SCENE = (
    "home office with bookshelf behind, polished wooden floor, "
    "daylight from a tall window"
)
VIDEO_CALL_SCENE_OVERRIDES = [
    "home office, bookshelf behind a tidy desk, wood floor, side window",
    "home office, plant wall behind, parquet floor in foreground",
    "loft home office, exposed brick wall behind, polished concrete floor",
    "home office, gradient color panel behind, hardwood floor",
]


# ---------------------------------------------------------------------------
# P1 — screen-facing scene rewrites
# ---------------------------------------------------------------------------
# Same template as :data:`fix_landmarks.LANDMARK_RECIPES`: concrete
# scene_anchor + 3-4 scene_overrides. The wording deliberately
# includes a foreground prop, a depth-bearing backdrop ("behind",
# "across the room") and at least one open / ambient light source
# (``daylight from a window`` / ``soft key from the side``).

P1_RECIPES: dict[str, dict[str, Any]] = {
    "analytics_review": {
        "base_scene": (
            "executive office, floor-to-ceiling windows behind, "
            "polished desk in foreground, daylight"
        ),
        "scene_anchor": (
            "executive office, floor-to-ceiling windows behind, "
            "polished desk in foreground, daylight"
        ),
        "scene_overrides": [
            "executive office, city skyline behind, wooden desk in foreground",
            "analytics office, white walls behind, marble floor in foreground",
            "boardroom office, mahogany table in foreground, dashboards behind",
        ],
    },
    "tech_developer": {
        "base_scene": (
            "developer studio, exposed brick wall behind, polished "
            "concrete floor in foreground, daylight from a side window"
        ),
        "scene_anchor": (
            "developer studio, exposed brick wall behind, polished "
            "concrete floor in foreground, daylight from a side window"
        ),
        "scene_overrides": [
            "tech studio, white wall behind, hardwood floor in foreground",
            "home office, RGB accent on back wall, concrete floor",
            "engineering loft, bookshelves behind, daylight from a side window",
        ],
    },
    "podcast": {
        "base_scene": (
            "podcast studio, acoustic panels and bookshelf behind, "
            "hardwood floor in foreground, warm side key light"
        ),
        "scene_anchor": (
            "podcast studio, acoustic panels and bookshelf behind, "
            "hardwood floor in foreground, warm side key light"
        ),
        "scene_overrides": [
            "broadcast booth, wood panelling behind, hardwood floor in foreground",
            "podcast studio, backlit foam wall behind, concrete floor",
            "podcast corner, bookshelf and string lights behind, hardwood floor",
        ],
    },
    "podcast_host": {
        "base_scene": (
            "podcast studio, acoustic foam wall behind, hardwood floor "
            "in foreground, warm side key light"
        ),
        "scene_anchor": (
            "podcast studio, acoustic foam wall behind, hardwood floor "
            "in foreground, warm side key light"
        ),
        "scene_overrides": [
            "broadcast studio, backlit panel wall behind, concrete floor",
            "podcast set, warm wood wall behind, daylight from a side window",
            "host corner, bookshelf and string lights behind, hardwood floor",
        ],
    },
    "youtube_creator": {
        "base_scene": (
            "creator studio, neon-lit backdrop wall behind, polished "
            "floor in foreground"
        ),
        "scene_anchor": (
            "creator studio, neon-lit backdrop wall behind, polished "
            "floor in foreground"
        ),
        "scene_overrides": [
            "creator studio, gradient color wall behind, hardwood floor",
            "content studio, bookshelf and plants behind, concrete floor",
            "creator loft, exposed brick wall behind, daylight from a tall window",
        ],
    },
}


# ---------------------------------------------------------------------------
# P2 — surgical depth-cue additions
# ---------------------------------------------------------------------------
# Same shape as P1 but the original scene wording is preserved; we
# only add a foreground / ambient daylight cue. Each entry rewrites
# scene_anchor + scene_overrides verbatim to the values below; if
# you want to keep a particular legacy override, list it here.

P2_RECIPES: dict[str, dict[str, Any]] = {
    "standing_desk": {
        "base_scene": (
            "home office, monitor on back wall, standing desk in "
            "foreground, wooden floor, window light"
        ),
        "scene_anchor": (
            "home office, monitor on back wall, standing desk in "
            "foreground, wooden floor, window light"
        ),
        "scene_overrides": [
            "home office, bookshelf behind, standing desk in foreground",
            "tech studio, wall-mounted monitors behind, concrete floor",
            "architect's desk, blueprints behind, hardwood floor in foreground",
            "art director's desk, mood board behind, wooden floor",
        ],
    },
    "online_learning": {
        "base_scene": (
            "study room, bookshelf behind, desk with laptop in "
            "foreground, hardwood floor, side window light"
        ),
        "scene_anchor": (
            "study room, bookshelf behind, desk with laptop in "
            "foreground, hardwood floor, side window light"
        ),
        "scene_overrides": [
            "study nook, wall lamp and bookshelf behind, desk in foreground",
            "home study, pinboard on back wall, wooden floor in foreground",
            "library room, bookshelves behind, desk in foreground",
        ],
    },
    "notebook_ideas": {
        "base_scene": (
            "creative workspace, mood-board wall behind, sketchbook on a "
            "desk in foreground, hardwood floor, side window light"
        ),
        "scene_anchor": (
            "creative workspace, mood-board wall behind, sketchbook on a "
            "desk in foreground, hardwood floor, side window light"
        ),
        "scene_overrides": [
            "cafe window, notebook on the table in foreground, wood floor",
            "library room, bookshelves behind, reading desk in foreground",
            "home study, notebook in foreground, bookshelf behind, hardwood floor",
        ],
    },
    "tablet_stylus": {
        "base_scene": (
            "creative studio, mood-board prints behind, drafting table "
            "in foreground, hardwood floor, ambient daylight"
        ),
        "scene_anchor": (
            "creative studio, mood-board prints behind, drafting table "
            "in foreground, hardwood floor, ambient daylight"
        ),
        "scene_overrides": [
            "design studio, concrete wall behind, glass desk in foreground",
            "art studio, white wall behind, hardwood floor in foreground",
            "creative loft, exposed brick wall behind, drafting table in foreground",
        ],
    },
    "late_hustle": {
        "base_scene": (
            "evening office, tall window behind, city lights visible, "
            "desk in foreground, hardwood floor, warm lamp"
        ),
        "scene_anchor": (
            "evening office, tall window behind, city lights visible, "
            "desk in foreground, hardwood floor, warm lamp"
        ),
        "scene_overrides": [
            "home office at night, skyline through a tall window behind, wooden desk",
            "corner office at night, skyline behind, concrete floor in foreground",
            "office at blue hour, bookshelf and skyline behind, hardwood floor",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, payload: str) -> None:
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=tmp_dir, text=False)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _apply_scene_recipe(entry: dict[str, Any], recipe: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    base_scene = recipe["base_scene"]
    scene_anchor = recipe["scene_anchor"]
    scene_overrides = list(recipe["scene_overrides"])

    if entry.get("base_scene") != base_scene:
        entry["base_scene"] = base_scene
        changed.append("base_scene")

    background = entry.setdefault("background", {})
    if background.get("base") != base_scene:
        background["base"] = base_scene
        changed.append("background.base")
    if background.get("overrides_allowed") != scene_overrides:
        background["overrides_allowed"] = scene_overrides
        changed.append("background.overrides_allowed")
    if background.get("lock") not in ("semi", "flexible"):
        background["lock"] = "semi"
        changed.append("background.lock")

    if entry.get("scene_anchor") != scene_anchor:
        entry["scene_anchor"] = scene_anchor
        changed.append("scene_anchor")
    if entry.get("scene_overrides") != scene_overrides:
        entry["scene_overrides"] = scene_overrides
        changed.append("scene_overrides")
    if entry.get("background_lock") not in ("semi", "flexible"):
        entry["background_lock"] = "semi"
        changed.append("background_lock")

    channels = entry.setdefault("available_channels", [])
    if "scene_override" not in channels:
        channels.append("scene_override")
        changed.append("available_channels.scene_override")

    # Trigger pool — anchor + overrides so the sampler has ≥3 distinct
    # phrasings (the ``test_curated_styles_have_rich_trigger_pool``
    # invariant) and the user gets visible variety across regenerations
    # of the same style.
    pool_target = [scene_anchor] + [s for s in scene_overrides if s != scene_anchor]
    if entry.get("trigger_pool") != pool_target:
        entry["trigger_pool"] = pool_target
        changed.append("trigger_pool")

    return changed


def _migrate_video_call(entry: dict[str, Any]) -> list[str]:
    changed = _apply_scene_recipe(
        entry,
        {
            "base_scene": VIDEO_CALL_BASE_SCENE,
            "scene_anchor": VIDEO_CALL_BASE_SCENE,
            "scene_overrides": VIDEO_CALL_SCENE_OVERRIDES,
        },
    )

    if entry.get("default_clothing") != VIDEO_CALL_WARDROBE:
        entry["default_clothing"] = VIDEO_CALL_WARDROBE
        changed.append("default_clothing")
    clothing_block = entry.setdefault("clothing", {})
    default_block = clothing_block.setdefault("default", {})
    for gender_key in ("male", "female", "neutral"):
        if default_block.get(gender_key) != VIDEO_CALL_WARDROBE:
            default_block[gender_key] = VIDEO_CALL_WARDROBE
            changed.append(f"clothing.default.{gender_key}")

    if entry.get("expression") != VIDEO_CALL_EXPRESSION:
        entry["expression"] = VIDEO_CALL_EXPRESSION
        changed.append("expression")

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(styles, list):
        print("ERROR: data/styles.json is not a JSON array.", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    changed_any = False

    for entry in styles:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id", "")
        if sid == "video_call":
            fields = _migrate_video_call(entry)
            records.append({"id": sid, "tier": "P0", "changed_fields": fields})
            if fields:
                changed_any = True
            continue
        recipe = P1_RECIPES.get(sid)
        tier = "P1"
        if recipe is None:
            recipe = P2_RECIPES.get(sid)
            tier = "P2" if recipe is not None else None
        if recipe is None:
            continue
        fields = _apply_scene_recipe(entry, recipe)
        records.append({"id": sid, "tier": tier, "changed_fields": fields})
        if fields:
            changed_any = True

    applied = sum(1 for r in records if r["changed_fields"])
    print(
        f"v1.71 indoor-depth migration: applied={applied} "
        f"recipes_total={len(records)}"
    )

    if not args.dry_run and changed_any:
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# v1.71 Indoor-depth normalization",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if args.dry_run else 'COMMIT'}`",
        f"- Recipes total: {len(records)}",
        f"- Applied (changed at least one field): {applied}",
        "",
        "## Per-style report",
        "",
        "| id | tier | fields touched |",
        "|---|---|---|",
    ]
    for r in sorted(records, key=lambda x: (x["tier"] or "", x["id"])):
        fields = ", ".join(r["changed_fields"]) or "—"
        lines.append(f"| `{r['id']}` | {r['tier']} | {fields} |")
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
