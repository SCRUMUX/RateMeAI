"""One-shot migration: ``clothing.default`` (str) -> dict {male, female, neutral}.

Phase 2 of the v1.27.3 prompt-personalisation work. The schema flip was
introduced in :mod:`src.prompts.style_schema_v2.ClothingSlot` and the
loader (:func:`src.services.style_loader_v2._clothing_default_dict`)
already accepts both shapes; this script normalises the on-disk JSON
so admins see the dict shape in the editor and the catalog API stops
emitting the legacy string.

Behaviour:

* Pass 1 — every v2 entry whose ``clothing.default`` is a plain string
  is converted to ``{"male": s, "female": s, "neutral": s}``. Entries
  whose ``clothing.default`` is already a dict are left alone (idempotent).
* Pass 2 — for a curated list of styles where the existing wording is
  obviously male-coded (e.g. Burj Khalifa, Wall Street, Brooklyn Bridge),
  the ``female`` key is replaced with a hand-curated female variant.
  ``male`` and ``neutral`` keep the original male phrasing so the bot
  still defaults to it for unknown / male profiles.

The override list is intentionally small. The new admin UI exposes
per-gender editors so non-engineers can extend the curation later
without touching this script.

Usage::

    python scripts/migrations/2026_04_gender_clothing/seed_clothing_dict.py
    python scripts/migrations/2026_04_gender_clothing/seed_clothing_dict.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"


# Hand-curated female phrasing for styles where the male variant on
# disk is obviously not gender-neutral. Keys MUST match `id` values in
# data/styles.json. Values are emitted into clothing.default["female"].
# We deliberately keep the list short; admins can expand it through
# the admin UI.
FEMALE_OVERRIDES: dict[str, str] = {
    "dubai_burj_khalifa": (
        "tailored dark blouse or fitted dress, slim trousers or pencil skirt, "
        "statement watch, polished modern style"
    ),
    "nyc_brooklyn_bridge": (
        "casual fitted jacket, dark jeans or wide-leg trousers, comfortable walking shoes"
    ),
    "rome_colosseum": (
        "linen blouse, light trousers or midi skirt, leather sandals, relaxed Italian style"
    ),
    "venice_san_marco": (
        "elegant smart-casual dress or fitted blazer with skirt, quality leather flats, "
        "refined style"
    ),
    "barcelona_sagrada": (
        "relaxed summer blouse or sundress, light trousers, straw hat, Mediterranean casual"
    ),
    "london_eye": (
        "tailored overcoat or trench, dark scarf, smart casual British layers"
    ),
    "tokyo_tower": (
        "minimal Japanese-inspired outfit, clean dark fitted layers or wrap dress"
    ),
    "singapore_marina_bay": (
        "smart fitted blouse, tailored dark trousers or skirt, polished modern flats"
    ),
    "sf_golden_gate": (
        "fitted fleece or casual jacket, dark jeans, relaxed outdoor-casual style"
    ),
    "athens_acropolis": (
        "relaxed white linen blouse or dress, light trousers, leather sandals"
    ),
    "sydney_opera": (
        "casual smart outfit, fitted blouse or summer dress, clean summer style"
    ),
    "nyc_times_square": (
        "streetwear layers, statement jacket, fitted dark pants or skirt, designer sneakers"
    ),
    "nyc_central_park": (
        "casual fitted sweater, dark jeans, clean casual sneakers"
    ),
    "london_big_ben": (
        "classic British smart-casual, tailored jacket or wrap dress, polished accessories"
    ),
    "rooftop_city": (
        "fitted blazer over fitted top, tailored trousers or skirt, minimalist watch"
    ),
    "gym_fitness": (
        "fitted athletic top or sports bra under crop hoodie, athletic leggings, training shoes"
    ),
    "running": (
        "lightweight running top, athletic shorts or leggings, running shoes, sport watch"
    ),
    "swimming_pool": (
        "fitted one-piece or sporty swimsuit, optional sunglasses in hand"
    ),
    "tennis": (
        "fitted polo or tennis dress, tennis skirt, wristband, clean white sneakers"
    ),
    "restaurant": (
        "tailored dark dress or fitted blouse with skirt, smart evening look, subtle accessories"
    ),
    "motorcycle": (
        "fitted leather jacket over plain tee, dark denim, motorcycle boots"
    ),
    "yacht": (
        "white linen blouse or summer dress, navy shorts or wide-leg trousers, deck shoes"
    ),
    "beach_sunset": (
        "flowy linen blouse or beach dress, rolled trousers or shorts, bare feet"
    ),
    "art_gallery": (
        "smart turtleneck or fitted blouse, tailored trousers or midi skirt, minimalist style"
    ),
}


def _atomic_write(path: Path, payload: str) -> None:
    """Write *payload* to *path* via a temp file + ``os.replace``."""
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


def migrate_style(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single style entry. Mutates in place.

    Returns a record describing what changed (for the summary output).
    """
    sid = str(entry.get("id") or "<unknown>")
    record = {"id": sid, "converted": False, "female_override": False}

    if int(entry.get("schema_version") or 0) != 2:
        return record

    clothing = entry.get("clothing")
    if not isinstance(clothing, dict):
        return record

    raw_default = clothing.get("default")

    # Pass 1 — string -> dict.
    if isinstance(raw_default, str):
        male = raw_default
        female = raw_default
        neutral = raw_default
        clothing["default"] = {
            "male": male,
            "female": female,
            "neutral": neutral,
        }
        record["converted"] = True
    elif isinstance(raw_default, dict):
        # Already dict — make sure all three keys exist (fill from neutral).
        male = str(raw_default.get("male") or "")
        female = str(raw_default.get("female") or "")
        neutral = str(raw_default.get("neutral") or "")
        fill = neutral or male or female
        clothing["default"] = {
            "male": male or fill,
            "female": female or fill,
            "neutral": neutral or fill,
        }
    else:
        # Unknown shape — skip silently.
        return record

    # Pass 2 — apply hand-curated female override.
    override = FEMALE_OVERRIDES.get(sid)
    if override and clothing["default"].get("female") != override:
        clothing["default"]["female"] = override
        record["female_override"] = True

    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the diff summary; do not modify data/styles.json.",
    )
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    summaries = [migrate_style(s) for s in styles]

    converted = [s for s in summaries if s["converted"]]
    overridden = [s for s in summaries if s["female_override"]]

    print(f"Total v2 styles processed: {sum(1 for _ in summaries)}")
    print(f"clothing.default: str -> dict conversions: {len(converted)}")
    print(f"hand-curated female overrides applied:    {len(overridden)}")
    print()
    for s in overridden:
        print(f"  {s['id']:32s}  female override")

    if args.dry_run:
        print()
        print("Dry-run: data/styles.json NOT written.")
        return 0

    if not converted and not overridden:
        print()
        print("No-op: every clothing.default is already in dict shape and matches the curation.")
        return 0

    payload = json.dumps(styles, indent=2, ensure_ascii=False) + "\n"
    _atomic_write(STYLES_PATH, payload)
    print()
    print(f"Wrote {STYLES_PATH.relative_to(REPO_ROOT)} ({len(payload):,} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
