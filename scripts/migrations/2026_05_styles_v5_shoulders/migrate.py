"""v1.70 Style Catalog Normalization — shoulder visibility cue.

This is the one-shot migration that complements the v1.70 wire-prompt
cleanup. After v1.70 removed every head-anchor clause from the wire
prompt (``_COMPOSITION_NUMERICAL_HINT``, ``_FACE_AREA_ANCHOR_BY_FRAMING``,
``head subtly turned``, lens / DoF block), the prompt no longer
carries any explicit cue for the model to render the shoulders. On
closed-shoulder wardrobes (blazer, polo, suit, sweater, knit) edit
models on FAL fall back to copying the head/torso ratio of the
reference photo verbatim — which on tight-selfie inputs reproduces
the "huge head" pathology.

The v1.70 audit (``docs/ANATOMY_INVESTIGATION.md`` F2) found that
``gym_fitness`` works *because* its ``clothing.default`` already
shows the shoulder line (``fitted athletic tank top``). This
migration generalises that property to every non-sport, non-document,
non-studio-portrait style by appending ``, shoulder line visible``
to ``default_clothing`` and ``clothing.default.{male,female,neutral}``
strings that don't already carry a shoulder cue.

The script is idempotent — a second run sees the appended cue and
leaves the field alone. Studio-portrait, document, and sport styles
are exempted via the whitelist below (they already carry shoulder
information by design or are explicitly tight headshots).

Usage::

    python scripts/migrations/2026_05_styles_v5_shoulders/migrate.py --dry-run
    python scripts/migrations/2026_05_styles_v5_shoulders/migrate.py
    python scripts/migrations/2026_05_styles_v5_shoulders/migrate.py --keys cafe restaurant
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
BACKUP_PATH = REPO_ROOT / "data" / "styles.json.bak.v169"


# Styles whose wardrobe must NOT receive the shoulder cue.
#
# * Studio portraits — tight headshot is the intended creative output.
# * Document styles — vendor format requires a tight head-and-shoulders
#   crop; the wire prompt for these intentionally carries head-anchor
#   wording (DOC_PRESERVE).
# * Sport styles — clothing already shows the shoulder pose by design
#   (tank top / running shirt / cycling jersey / yoga top / etc.).
# * Tinder-pack mini bundles — already optimised, leave alone.
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
_SPORT_STYLE_KEYS: frozenset[str] = frozenset(
    {
        "gym_fitness",
        "running",
        "tennis",
        "swimming_pool",
        "hiking",
        "yoga_outdoor",
        "cycling",
    }
)
EXEMPT_KEYS: frozenset[str] = (
    _STUDIO_PORTRAIT_STYLE_KEYS
    | _DOCUMENT_STYLE_KEYS
    | _SPORT_STYLE_KEYS
)


# Regex that detects an existing shoulder cue. Idempotency lever:
# if any of these patterns already match the wardrobe string the
# field is left alone.
#
# Recognised cues:
# * "shoulder" / "shoulders" — plain anatomical mention.
# * "shoulder line" — the wording introduced by this migration.
# * "well-fitted across the shoulders" — v1.66 (v4 anatomy) wording.
# * "natural shoulder" — older curated wording.
_EXISTING_SHOULDER_CUE_PATTERN = re.compile(
    r"\b("
    r"shoulders?"
    r"|shoulder\s+line"
    r"|well-fitted\s+across\s+the\s+shoulders"
    r"|natural\s+shoulder"
    r"|tank\s+top"
    r"|sports?\s+bra"
    r"|sleeveless"
    r")\b",
    re.IGNORECASE,
)

_SHOULDER_CUE_APPEND = ", shoulder line visible"


def _maybe_append_shoulder_cue(value: str) -> tuple[str, bool]:
    """Return (new_value, was_changed).

    Appends the shoulder cue only if the input is a non-empty string
    that does not already mention the shoulder line. Trims a trailing
    period before appending so the rewritten string stays a single
    natural-language fragment.
    """
    if not isinstance(value, str) or not value.strip():
        return value, False
    if _EXISTING_SHOULDER_CUE_PATTERN.search(value):
        return value, False
    return value.rstrip().rstrip(".") + _SHOULDER_CUE_APPEND, True


def migrate_style(entry: dict[str, Any]) -> dict[str, Any]:
    sid = entry.get("id", "<unknown>")
    record: dict[str, Any] = {
        "id": sid,
        "status": "untouched",
        "default_clothing_changed": False,
        "clothing_default_changed": 0,
    }

    if sid in EXEMPT_KEYS:
        record["status"] = "exempt"
        return record

    touched = False

    # default_clothing (legacy field used by v1/v2 codepath)
    new_dc, dc_changed = _maybe_append_shoulder_cue(
        entry.get("default_clothing", "")
    )
    if dc_changed:
        entry["default_clothing"] = new_dc
        record["default_clothing_changed"] = True
        touched = True

    # clothing.default.{male,female,neutral} (v3 schema)
    clothing_block = entry.get("clothing")
    if isinstance(clothing_block, dict):
        default_block = clothing_block.get("default")
        if isinstance(default_block, dict):
            for gender_key in ("male", "female", "neutral"):
                new_val, added = _maybe_append_shoulder_cue(
                    default_block.get(gender_key, "")
                )
                if added:
                    default_block[gender_key] = new_val
                    record["clothing_default_changed"] += 1
                    touched = True

    if touched:
        record["status"] = "migrated"
    return record


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
        "# v1.70 Style Catalog Normalization — migration log",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if dry_run else 'COMMIT'}`",
        f"- Total styles: {len(records)}",
        f"- Migrated: {len(migrated)}",
        f"- Exempt (studio/document/sport): {len(exempt)}",
        f"- Untouched (already carry a shoulder cue): {len(untouched)}",
        "",
        "## Migrated styles",
        "",
        "| id | default_clothing | clothing.default.* |",
        "|---|---|---|",
    ]
    for r in sorted(migrated, key=lambda x: x["id"]):
        lines.append(
            f"| `{r['id']}` | "
            f"{'yes' if r['default_clothing_changed'] else 'no'} | "
            f"{r['clothing_default_changed']} |"
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
                "default_clothing_changed": False,
                "clothing_default_changed": 0,
            })
            continue
        records.append(migrate_style(entry))

    migrated_count = sum(1 for r in records if r["status"] == "migrated")
    exempt_count = sum(1 for r in records if r["status"] == "exempt")
    untouched_count = sum(1 for r in records if r["status"] == "untouched")

    print(
        f"v1.70 shoulder-visibility migration: "
        f"migrated={migrated_count} exempt={exempt_count} "
        f"untouched={untouched_count}"
    )

    if not args.dry_run and migrated_count:
        if not BACKUP_PATH.exists():
            shutil.copy2(STYLES_PATH, BACKUP_PATH)
            print(f"Backup written to {BACKUP_PATH}")
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    _write_log(records, dry_run=args.dry_run)
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
