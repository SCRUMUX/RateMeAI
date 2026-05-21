"""v1.71 Style Catalog Normalization — strong shoulder cue.

Background
----------

The v5 migration (``2026_05_styles_v5_shoulders``) appended a weak
``, shoulder line visible`` cue to ``default_clothing`` and
``clothing.default.{male,female,neutral}`` for 121 styles. The
follow-up production audit (May 2026) showed that the weak cue is
not strong enough for FAL edit models on tight-selfie references:
``rome_colosseum`` still produced the "glued head" pathology while
``legal_finance`` did not.

The structural difference between the two: ``legal_finance``
(and 5 other v1.66 career styles — corporate, boardroom,
glass_wall_pose, decision_moment, speaker_stage) carry the
**strong** v1.66 paint ``, well-fitted across the shoulders`` —
a geometric instruction about how the garment fits, not just an
abstract "the line is visible" statement. Edit-models translate
the v1.66 wording into a concrete shoulder geometry in the output;
the v5 wording is treated as a soft cue and is often ignored.

This migration generalises the strong cue across the catalogue,
adapted per garment type so the wording stays natural:

| Garment family                       | Strong cue                                       |
| ------------------------------------ | ------------------------------------------------ |
| suit, blazer, jacket, tailored top   | well-fitted across the shoulders                 |
| coat, overcoat, trench, parka        | coat shoulders visible across the upper frame    |
| shirt, polo, henley, button-down     | collar and shoulder seam clearly visible         |
| dress, blouse, top, knit             | shoulders fully in frame                         |
| sweater, hoodie, cardigan, turtleneck| fit shows the natural shoulder line              |
| tee, t-shirt, tank, sleeveless       | crew-neck shoulder line clearly visible          |
| other / casual catch-all             | shoulders fully in frame                         |

The script is idempotent: it (a) rewrites any string that ends
with the v5 cue, (b) leaves alone strings that already carry one
of the v1.66 strong cues, (c) skips the exempt whitelist (sport /
document / studio-portrait styles whose wardrobe is by design either
sleeveless or strictly tight-crop).

Usage::

    python scripts/migrations/2026_05_styles_v6_strong_shoulders/migrate.py --dry-run
    python scripts/migrations/2026_05_styles_v6_strong_shoulders/migrate.py
    python scripts/migrations/2026_05_styles_v6_strong_shoulders/migrate.py --keys cafe restaurant
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
BACKUP_PATH = REPO_ROOT / "data" / "styles.json.bak.v170"


# Styles whose wardrobe must NOT receive any shoulder cue.
# Same set as v5 migration — wardrobe is either already sleeveless
# (sport), strictly studio-tight (formal_portrait / studio_elegant),
# or a vendor-locked document format (passport / visa / 3x4 / 4x6).
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


# Strong cues (v1.71). The migration converts the v5 weak cue into
# one of these depending on the garment family it detects.
CUE_SUIT = "well-fitted across the shoulders"
CUE_COAT = "coat shoulders visible across the upper frame"
CUE_SHIRT = "collar and shoulder seam clearly visible"
CUE_KNIT = "fit shows the natural shoulder line"
CUE_TEE = "crew-neck shoulder line clearly visible"
CUE_DEFAULT = "shoulders fully in frame"

ALL_STRONG_CUES: frozenset[str] = frozenset(
    {CUE_SUIT, CUE_COAT, CUE_SHIRT, CUE_KNIT, CUE_TEE, CUE_DEFAULT}
)

# The exact wording we are migrating away from (added by v5).
WEAK_CUE = "shoulder line visible"

# Garment-type matchers. Order matters: the first hit wins.
# Patterns are case-insensitive substrings of the wardrobe string
# (with the trailing weak cue already stripped).
_GARMENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Suits / blazers / tailored layers — strongest classical pattern.
    (re.compile(r"\b(suit|blazer|tailored|three-piece|tweed|tuxedo)\b", re.IGNORECASE), CUE_SUIT),
    # Coats / overcoats / outerwear — winter / rain layers.
    (re.compile(r"\b(overcoat|trench|parka|topcoat|peacoat|duffle)\b", re.IGNORECASE), CUE_COAT),
    (re.compile(r"\b(wool\s+coat|leather\s+coat|raincoat|coat)\b", re.IGNORECASE), CUE_COAT),
    # Shirts / polos / formal collared tops.
    (re.compile(r"\b(button-down|button\s+down|oxford\s+shirt|dress\s+shirt|polo)\b", re.IGNORECASE), CUE_SHIRT),
    (re.compile(r"\b(linen\s+shirt|cotton\s+shirt|fitted\s+shirt|crisp\s+shirt|button-up)\b", re.IGNORECASE), CUE_SHIRT),
    (re.compile(r"\b(shirt|blouse)\b", re.IGNORECASE), CUE_SHIRT),
    # Knit family.
    (
        re.compile(
            r"\b(knit(?:\s+top)?|cardigan|cashmere|turtleneck|henley|fleece|sweatshirt|pullover|sweater|hoodie)\b",
            re.IGNORECASE,
        ),
        CUE_KNIT,
    ),
    # Tees / tanks (the sleeveless cohort never gets a cue per
    # ``EXEMPT_KEYS`` for sport, but lifestyle tees may exist).
    (re.compile(r"\b(crew[-\s]neck|t[-\s]?shirt|\btee\b|tank|sleeveless)\b", re.IGNORECASE), CUE_TEE),
    # Dresses / midi / skirts — feminine slot.
    (re.compile(r"\b(dress|sundress|midi|skirt|jumpsuit|kimono|kaftan)\b", re.IGNORECASE), CUE_DEFAULT),
    # Jackets / outerwear casual (must come AFTER suit/coat).
    (re.compile(r"\b(leather\s+jacket|denim\s+jacket|bomber|jacket)\b", re.IGNORECASE), CUE_SUIT),
)


def _classify_garment(text: str) -> str:
    """Return the strong cue best matching the wardrobe string.

    Falls back to :data:`CUE_DEFAULT` when no pattern matches.
    """
    sample = text or ""
    for pattern, cue in _GARMENT_PATTERNS:
        if pattern.search(sample):
            return cue
    return CUE_DEFAULT


def _normalise_wardrobe(value: str) -> tuple[str, bool, str | None]:
    """Return ``(new_value, changed, applied_cue)``.

    Conservative: only migrate strings that explicitly end with the
    v5 weak cue (``shoulder line visible``). Strings that already
    carry a strong cue stay as-is; strings that carry no recognised
    cue are left alone (covers document / studio / sport styles
    whose wardrobe was intentionally untouched in v5).
    """
    if not isinstance(value, str) or not value.strip():
        return value, False, None

    cleaned = value.rstrip().rstrip(",.;:!? ")
    cleaned_lower = cleaned.lower()

    # 1. Already strong — leave alone.
    for cue in ALL_STRONG_CUES:
        if cleaned_lower.endswith(cue.lower()):
            return value, False, None

    # 2. Weak v5 cue — strip and re-classify.
    if cleaned_lower.endswith(WEAK_CUE.lower()):
        body = cleaned[: -len(WEAK_CUE)].rstrip().rstrip(",")
        applied = _classify_garment(body)
        return f"{body}, {applied}", True, applied

    # 3. No recognised cue — defensive no-op. This branch covers
    # document / studio / sport wardrobes that intentionally do not
    # carry a shoulder cue; the v6 migration is not the place to add
    # one to them.
    return value, False, None


def _migrate_value(value: str) -> tuple[str, bool, str | None]:
    """Thin alias for :func:`_normalise_wardrobe` so the migration log
    can refer to "values" generically.
    """
    return _normalise_wardrobe(value)


def migrate_style(entry: dict[str, Any]) -> dict[str, Any]:
    sid = entry.get("id", "<unknown>")
    record: dict[str, Any] = {
        "id": sid,
        "status": "untouched",
        "default_clothing_changed": False,
        "clothing_default_changed": 0,
        "coherence_overrides_changed": 0,
        "applied_cues": set(),
    }

    if sid in EXEMPT_KEYS:
        record["status"] = "exempt"
        return record

    touched = False

    new_dc, dc_changed, dc_cue = _migrate_value(
        entry.get("default_clothing", "")
    )
    if dc_changed:
        entry["default_clothing"] = new_dc
        record["default_clothing_changed"] = True
        if dc_cue:
            record["applied_cues"].add(dc_cue)
        touched = True

    clothing_block = entry.get("clothing")
    if isinstance(clothing_block, dict):
        default_block = clothing_block.get("default")
        if isinstance(default_block, dict):
            for gender_key in ("male", "female", "neutral"):
                new_val, added, applied_cue = _migrate_value(
                    default_block.get(gender_key, "")
                )
                if added:
                    default_block[gender_key] = new_val
                    record["clothing_default_changed"] += 1
                    if applied_cue:
                        record["applied_cues"].add(applied_cue)
                    touched = True

    # Coherence-rule clothing overrides also need the strong cue —
    # otherwise a season swap (winter → wool coat) silently regresses
    # back to the v5 weak phrasing on first roll.
    coherence = entry.get("coherence")
    if isinstance(coherence, list):
        for rule in coherence:
            if not isinstance(rule, dict):
                continue
            clothing_override = rule.get("clothing_override")
            if not isinstance(clothing_override, dict):
                continue
            for gender_key in ("male", "female", "neutral"):
                new_val, added, applied_cue = _migrate_value(
                    clothing_override.get(gender_key, "")
                )
                if added:
                    clothing_override[gender_key] = new_val
                    record["coherence_overrides_changed"] += 1
                    if applied_cue:
                        record["applied_cues"].add(applied_cue)
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
        "# v1.71 Style Catalog Normalization — strong shoulder cue",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if dry_run else 'COMMIT'}`",
        f"- Total styles: {len(records)}",
        f"- Migrated: {len(migrated)}",
        f"- Exempt (studio/document/sport): {len(exempt)}",
        f"- Untouched (already carry a strong cue): {len(untouched)}",
        "",
        "## Migrated styles",
        "",
        "| id | default_clothing | clothing.default.* | coherence.* | applied cues |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(migrated, key=lambda x: x["id"]):
        cues = ", ".join(sorted(r["applied_cues"])) or "—"
        lines.append(
            f"| `{r['id']}` | "
            f"{'yes' if r['default_clothing_changed'] else 'no'} | "
            f"{r['clothing_default_changed']} | "
            f"{r['coherence_overrides_changed']} | "
            f"{cues} |"
        )
    if exempt:
        lines.append("")
        lines.append("## Exempt styles (untouched by design)")
        lines.append("")
        for r in sorted(exempt, key=lambda x: x["id"]):
            lines.append(f"- `{r['id']}`")
    if untouched:
        lines.append("")
        lines.append("## Untouched styles (already carry a strong cue)")
        lines.append("")
        for r in sorted(untouched, key=lambda x: x["id"]):
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
                "coherence_overrides_changed": 0,
                "applied_cues": set(),
            })
            continue
        records.append(migrate_style(entry))

    migrated_count = sum(1 for r in records if r["status"] == "migrated")
    exempt_count = sum(1 for r in records if r["status"] == "exempt")
    untouched_count = sum(1 for r in records if r["status"] == "untouched")

    print(
        f"v1.71 strong-shoulder migration: "
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
