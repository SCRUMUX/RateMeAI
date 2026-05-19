"""v1.66 Style Catalog Normalization — anatomy-proportions cleanup.

This is the one-shot migration that complements the v1.65 prompt-assembly
fix. v1.65 made the wire prompt consistent across styles (single
``_COMPOSITION_NUMERICAL_HINT`` anchor + ``IDENTITY_PRESERVE_BLOCK`` + no
duplicate framing line). After v1.65 deployed, generations on
``gym_fitness`` / ``dating_park`` / ``hiking`` came out with correct
head-to-body proportions, but ``legal_finance`` / ``boardroom`` /
``video_call`` (and a handful of dating + social styles) still produced
"giant head" artefacts despite identical inputs and prompt structure.

Root cause: the *style data* in ``data/styles.json`` carries hidden
portrait-pose directives that semantically conflict with the cinematic
composition anchor:

* **``expression``** strings encoded a "studio headshot mood":
  ``Authoritative steady expression, distinguished gravitas, composed
  gaze``, ``Authoritative composed expression, steady leadership gaze``,
  ``Strong thoughtful expression, composed decisive brow, executive
  vision``, etc. Edit models read those as "render this person as a
  cropped studio portrait" — overriding the explicit ``bust shot at
  natural human head-to-body scale`` instruction earlier in the prompt.

* **``scene_anchor`` / ``base_scene``** for a few professional styles
  encoded implicit poses: ``leather chair`` (sitting down → body
  compressed → head dominates), ``webcam-friendly framing`` (literally
  asks for a tight crop), ``behind a desk`` (similar geometry).

* **``default_clothing``** for tailored suits described tight silhouettes
  without an explicit shoulder cue, which the model interpreted as
  "shoulders pulled in / collar high" — also makes the head look
  oversized relative to the visible torso.

v1.66 normalises all three fields across the catalog in one idempotent
pass, leaving studio-portrait styles (``formal_portrait``,
``studio_elegant``) and document styles (``photo_3x4``, ``passport_rf``,
``visa_eu`` / ``visa_us``, ``photo_4x6``, ``driver_license``) untouched
— those genres *are* tight headshots by design.

The script is fully token-level: it does NOT rewrite whole records.
Each rewrite is a deterministic ``before -> after`` mapping pulled from
the curated tables below, applied to every field that may carry the
problematic phrasing. Running the script a second time is a no-op
because the rewrites only fire on the v1.65 (pre-normalisation) form.

Usage::

    python scripts/migrations/2026_05_styles_v4_anatomy/migrate.py --dry-run
    python scripts/migrations/2026_05_styles_v4_anatomy/migrate.py
    python scripts/migrations/2026_05_styles_v4_anatomy/migrate.py --keys legal_finance boardroom
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LOG_PATH = Path(__file__).resolve().parent / "MIGRATION_LOG.md"
BACKUP_PATH = REPO_ROOT / "data" / "styles.json.bak.v165"


# Styles whose genre is "tight studio headshot by design" — must NOT be
# touched by any of the rewrites below. Mirrors
# ``src.prompts.image_gen._STUDIO_PORTRAIT_STYLE_KEYS`` and
# ``_DOCUMENT_STYLE_KEYS``; kept inlined here so this migration script
# stays runnable as a standalone tool (no src/ import).
_STUDIO_PORTRAIT_STYLE_KEYS: frozenset[str] = frozenset(
    {
        "formal_portrait",
        "studio_elegant",
    }
)
_DOCUMENT_STYLE_KEYS: frozenset[str] = frozenset(
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
EXEMPT_KEYS: frozenset[str] = _STUDIO_PORTRAIT_STYLE_KEYS | _DOCUMENT_STYLE_KEYS


# ---------------------------------------------------------------------------
# expression rewrites — match exact full strings produced by the v1.65
# catalog. Keys are the BEFORE form, values are the AFTER form. The
# wording is curated to (a) keep the same emotional register, (b)
# avoid the "studio portrait" lexical cluster, and (c) add an explicit
# "shoulders visible in frame" cue where the genre's clothing/scene
# benefits from one.
# ---------------------------------------------------------------------------

EXPRESSION_REWRITES: dict[str, str] = {
    # --- CV / professional ---------------------------------------------------
    "Authoritative steady expression, distinguished gravitas, composed gaze.": (
        "Confident relaxed expression, settled direct gaze, "
        "natural mouth line, shoulders visible in frame."
    ),
    "Authoritative composed expression, steady leadership gaze, strong confident brow.": (
        "Confident open expression, relaxed direct gaze, "
        "natural brow, shoulders visible in frame."
    ),
    "Strong thoughtful expression, composed decisive brow, executive vision.": (
        "Open thoughtful expression, relaxed brow, "
        "natural forward presence."
    ),
    "Engaging animated expression, commanding charismatic presence, confident forward gaze.": (
        "Engaging open expression, animated relaxed brow, "
        "natural forward presence."
    ),
    "Trustworthy direct gaze, professional confident half-smile, composed still mouth.": (
        "Confident open gaze, professional natural half-smile, "
        "relaxed mouth line."
    ),
    "Focused composed gaze, subtle prepared smile, polished professional still mouth.": (
        "Focused open gaze, subtle prepared smile, "
        "relaxed mouth line."
    ),
    "Composed powerful gaze, modern executive steady brow, confident expression.": (
        "Open confident gaze, modern relaxed brow, "
        "natural expression."
    ),
    "Composed traveler expression, confident relaxed smile, premium professional gaze.": (
        "Open traveler expression, confident relaxed smile, "
        "premium natural gaze."
    ),
    "Thoughtful composed gaze, deep contemplative expression, scholarly refined brow.": (
        "Open thoughtful gaze, contemplative natural expression, "
        "scholarly relaxed brow."
    ),
    # --- Dating / lifestyle --------------------------------------------------
    "Polished confident gaze, subtle sophisticated smile, composed worldly eyes.": (
        "Open confident gaze, sophisticated subtle smile, "
        "relaxed eyes."
    ),
    "Easy composed smile, composed worldly gaze, confident worldly expression.": (
        "Easy natural smile, open relaxed gaze, "
        "confident open expression."
    ),
    "Calm composed gaze, subtle confident expression, minimalist refined mouth.": (
        "Calm open gaze, subtle confident expression, "
        "relaxed mouth line."
    ),
    "Confident direct gaze, purposeful composed expression, polished still mouth.": (
        "Confident open gaze, purposeful relaxed expression, "
        "natural mouth line."
    ),
    "Direct assured gaze, subtle half-smile, relaxed brow and steady mouth.": (
        "Direct assured gaze, subtle half-smile, "
        "relaxed brow and natural mouth."
    ),
    "Strong direct gaze, calm rugged brow, bold closed-mouth line.": (
        "Direct confident gaze, calm rugged brow, "
        "natural closed-mouth line."
    ),
    "Composed sophisticated gaze, subtle confident smile, polished still mouth.": (
        "Open sophisticated gaze, subtle confident smile, "
        "relaxed mouth line."
    ),
    "Composed modern gaze, subtle power smile, cosmopolitan confident eyes.": (
        "Open modern gaze, subtle confident smile, "
        "cosmopolitan natural eyes."
    ),
    "Bold confident expression, steady urban gaze, effortless cool look.": (
        "Bold confident expression, open urban gaze, "
        "effortless cool look."
    ),
    "Thoughtful composed expression, subtle warm smile, elegant understated eyes.": (
        "Thoughtful open expression, subtle warm smile, "
        "elegant understated eyes."
    ),
    "Composed British elegance, subtle confident smile, refined worldly gaze.": (
        "Open British elegance, subtle confident smile, "
        "refined worldly gaze."
    ),
    "Warm confident smile, polished traveler gaze, composed expression.": (
        "Warm confident smile, polished traveler gaze, "
        "natural open expression."
    ),
    "Composed confident expression, subtle assured smile, elevated still brow.": (
        "Open confident expression, subtle assured smile, "
        "elevated relaxed brow."
    ),
    "Romantic composed expression, warm charming smile, elegant European gaze.": (
        "Romantic open expression, warm charming smile, "
        "elegant European gaze."
    ),
    # --- Social / aesthetic --------------------------------------------------
    "Intense direct gaze, bold edgy steady mouth, bold confident expression.": (
        "Direct open gaze, bold edgy relaxed mouth, "
        "bold confident expression."
    ),
    "Direct gaze, composed minimal expression, sharp modern still brow.": (
        "Direct open gaze, minimal natural expression, "
        "sharp modern relaxed brow."
    ),
    "Confident forward gaze, dynamic purposeful stride, bold expression.": (
        "Confident forward gaze, dynamic purposeful stride, "
        "bold open expression."
    ),
    "Contemplative expression, profound calm gaze, grand-scale composed brow.": (
        "Contemplative open expression, calm direct gaze, "
        "relaxed natural brow."
    ),
    "Calm confident gaze, effortless polished still mouth, composed expression.": (
        "Calm confident gaze, effortless polished smile, "
        "open expression."
    ),
    "Composed serene expression, elevated sophisticated still mouth, calm gaze.": (
        "Open serene expression, elevated sophisticated smile, "
        "calm gaze."
    ),
    "Intellectual composed expression, subtle confident gaze, cultured refined mouth.": (
        "Intellectual open expression, subtle confident gaze, "
        "cultured relaxed mouth."
    ),
    "Editorial confident expression, polished still mouth, striking gaze.": (
        "Editorial confident expression, polished natural smile, "
        "striking gaze."
    ),
    "Calm confident gaze, serene sophisticated still mouth, poised expression.": (
        "Calm confident gaze, serene sophisticated smile, "
        "poised expression."
    ),
}


# ---------------------------------------------------------------------------
# scene rewrites — applied to ``base_scene``, ``background.base``,
# ``scene_anchor`` and every entry of ``scene_overrides`` /
# ``trigger_pool`` / ``background.overrides_allowed``. Keys are full
# fragment strings; values strip the "implicit pose" cue while keeping
# the scene description intact.
# ---------------------------------------------------------------------------

SCENE_REWRITES: dict[str, str] = {
    "executive boardroom, polished dark table, leather chairs, large screen or whiteboard behind, even overhead lighting": (
        "executive boardroom interior, polished dark table edge across the background, "
        "large screen or whiteboard visible, soft even overhead lighting"
    ),
    "executive boardroom, polished dark table, leather chairs, large screen or whiteboard behind": (
        "executive boardroom interior, polished dark table edge across the background, "
        "large screen or whiteboard visible"
    ),
    "wood-paneled office or library, law books on shelves, warm ambient desk lamp, leather chair": (
        "wood-panelled office interior, law books on shelves, "
        "warm ambient desk lamp glow, soft daylight wash"
    ),
    "wood-paneled office or library, law books on shelves, leather chair": (
        "wood-panelled office interior, law books on shelves, "
        "soft daylight wash"
    ),
    "wood-paneled office with leather chair": (
        "wood-panelled office interior with soft daylight wash"
    ),
    "clean home office with ring light or monitor glow, neat bookshelves behind, webcam-friendly framing, even lighting": (
        "clean home office interior, ring light or monitor glow on the subject, "
        "neat bookshelves visible behind, even lighting"
    ),
    "clean home office with ring light or monitor glow, neat bookshelves behind, webcam-friendly framing": (
        "clean home office interior, ring light or monitor glow on the subject, "
        "neat bookshelves visible behind"
    ),
}


# ---------------------------------------------------------------------------
# clothing rewrites — append an explicit shoulder cue to tailored-suit
# strings that lack one. The regex finds the suit token and (only if
# no shoulder cue is already present) appends ``, well-fitted across
# the shoulders``. This is idempotent: a second run finds the cue and
# leaves the field alone.
# ---------------------------------------------------------------------------

_SUIT_PATTERN = re.compile(
    r"\b("
    r"three-piece\s+suit|"
    r"tailored\s+\w*\s*suit|"
    r"navy\s+suit|"
    r"charcoal\s+suit|"
    r"formal\s+suit|"
    r"dark\s+formal\s+suit|"
    r"tailored\s+dark\s+suit|"
    r"tailored\s+formal\s+charcoal\s+suit"
    r")\b",
    re.IGNORECASE,
)

_SHOULDER_CUE_PATTERN = re.compile(
    r"\b(shoulders?|shoulder\s+line|well-fitted\s+across\s+the\s+shoulders|"
    r"natural\s+shoulder)\b",
    re.IGNORECASE,
)

_SHOULDER_CUE_APPEND = ", well-fitted across the shoulders"


def _maybe_append_shoulder_cue(value: str) -> tuple[str, bool]:
    if not isinstance(value, str) or not value:
        return value, False
    if not _SUIT_PATTERN.search(value):
        return value, False
    if _SHOULDER_CUE_PATTERN.search(value):
        return value, False
    return value.rstrip().rstrip(".") + _SHOULDER_CUE_APPEND, True


# ---------------------------------------------------------------------------
# Per-style application
# ---------------------------------------------------------------------------


def _rewrite_string(value: Any, table: dict[str, str]) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False
    out = table.get(value, value)
    return out, out != value


def _rewrite_str_list(values: Any, table: dict[str, str]) -> tuple[Any, int]:
    if not isinstance(values, list):
        return values, 0
    out: list[Any] = []
    hits = 0
    for item in values:
        if isinstance(item, str) and item in table:
            out.append(table[item])
            hits += 1
        else:
            out.append(item)
    return out, hits


def migrate_style(entry: dict[str, Any]) -> dict[str, Any]:
    sid = entry.get("id", "<unknown>")
    record: dict[str, Any] = {
        "id": sid,
        "status": "untouched",
        "expression_rewritten": False,
        "scene_rewrites": 0,
        "clothing_appended": 0,
    }

    if sid in EXEMPT_KEYS:
        record["status"] = "exempt"
        return record

    touched = False

    # --- expression ----------------------------------------------------------
    new_expr, expr_changed = _rewrite_string(entry.get("expression"), EXPRESSION_REWRITES)
    if expr_changed:
        entry["expression"] = new_expr
        record["expression_rewritten"] = True
        touched = True

    # --- scene fields --------------------------------------------------------
    scene_hits = 0
    for field_name in ("base_scene", "scene_anchor"):
        new_val, changed = _rewrite_string(entry.get(field_name), SCENE_REWRITES)
        if changed:
            entry[field_name] = new_val
            scene_hits += 1
            touched = True

    bg = entry.get("background")
    if isinstance(bg, dict):
        new_base, bg_changed = _rewrite_string(bg.get("base"), SCENE_REWRITES)
        if bg_changed:
            bg["base"] = new_base
            scene_hits += 1
            touched = True
        new_overrides, list_hits = _rewrite_str_list(
            bg.get("overrides_allowed"), SCENE_REWRITES
        )
        if list_hits:
            bg["overrides_allowed"] = new_overrides
            scene_hits += list_hits
            touched = True

    for list_field in ("scene_overrides", "trigger_pool"):
        new_list, list_hits = _rewrite_str_list(entry.get(list_field), SCENE_REWRITES)
        if list_hits:
            entry[list_field] = new_list
            scene_hits += list_hits
            touched = True

    record["scene_rewrites"] = scene_hits

    # --- clothing ------------------------------------------------------------
    clothing_appends = 0

    new_clothing, append_added = _maybe_append_shoulder_cue(entry.get("default_clothing", ""))
    if append_added:
        entry["default_clothing"] = new_clothing
        clothing_appends += 1
        touched = True

    clothing_block = entry.get("clothing")
    if isinstance(clothing_block, dict):
        default_block = clothing_block.get("default")
        if isinstance(default_block, dict):
            for gender_key in ("male", "female", "neutral"):
                new_val, added = _maybe_append_shoulder_cue(default_block.get(gender_key, ""))
                if added:
                    default_block[gender_key] = new_val
                    clothing_appends += 1
                    touched = True

    record["clothing_appended"] = clothing_appends

    if touched:
        record["status"] = "migrated"
    return record


# ---------------------------------------------------------------------------
# IO helpers
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


def _write_log(records: list[dict[str, Any]], *, dry_run: bool) -> None:
    migrated = [r for r in records if r["status"] == "migrated"]
    exempt = [r for r in records if r["status"] == "exempt"]
    untouched = [r for r in records if r["status"] == "untouched"]

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# v1.66 Style Catalog Normalization — migration log",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if dry_run else 'COMMIT'}`",
        f"- Total styles: {len(records)}",
        f"- Migrated: {len(migrated)}",
        f"- Exempt (studio/document): {len(exempt)}",
        f"- Untouched (already normalised or not affected): {len(untouched)}",
        "",
        "## Migrated styles",
        "",
        "| id | expression | scene-rewrites | shoulder-cue |",
        "|---|---|---|---|",
    ]
    for r in sorted(migrated, key=lambda x: x["id"]):
        lines.append(
            f"| `{r['id']}` | "
            f"{'yes' if r['expression_rewritten'] else 'no'} | "
            f"{r['scene_rewrites']} | "
            f"{r['clothing_appended']} |"
        )
    if exempt:
        lines.append("")
        lines.append("## Exempt styles (untouched by design)")
        lines.append("")
        for r in sorted(exempt, key=lambda x: x["id"]):
            lines.append(f"- `{r['id']}`")
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the summary without writing data/styles.json.",
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        default=None,
        help="Only normalise the specified style ids.",
    )
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(styles, list):
        print("ERROR: data/styles.json is not a JSON array.", file=sys.stderr)
        return 2

    targets = set(args.keys) if args.keys else None

    records: list[dict[str, Any]] = []
    for entry in styles:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id", "")
        if targets is not None and sid not in targets:
            records.append({
                "id": sid,
                "status": "untouched",
                "expression_rewritten": False,
                "scene_rewrites": 0,
                "clothing_appended": 0,
            })
            continue
        records.append(migrate_style(entry))

    migrated = [r for r in records if r["status"] == "migrated"]
    exempt = [r for r in records if r["status"] == "exempt"]
    untouched = [r for r in records if r["status"] == "untouched"]

    print(f"Total styles: {len(records)}")
    print(f"  migrated:   {len(migrated)}")
    print(f"  exempt:     {len(exempt)}")
    print(f"  untouched:  {len(untouched)}")
    if migrated:
        print()
        print("Migrated styles:")
        for r in sorted(migrated, key=lambda x: x["id"]):
            print(
                f"  - {r['id']:32s}  expr={r['expression_rewritten']!s:>5s}  "
                f"scene={r['scene_rewrites']:>2d}  shoulder={r['clothing_appended']:>2d}"
            )

    _write_log(records, dry_run=args.dry_run)
    print()
    print(f"Wrote {LOG_PATH.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print()
        print("Dry-run: data/styles.json NOT written.")
        return 0

    if not BACKUP_PATH.exists():
        shutil.copy2(STYLES_PATH, BACKUP_PATH)
        print(f"Backup written: {BACKUP_PATH.relative_to(REPO_ROOT)}")

    payload = json.dumps(styles, indent=2, ensure_ascii=False) + "\n"
    _atomic_write(STYLES_PATH, payload)
    print(f"Wrote {STYLES_PATH.relative_to(REPO_ROOT)} ({len(payload):,} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
