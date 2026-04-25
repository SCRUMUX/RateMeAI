"""One-shot migration: tag tinder-pack styles with ``scenario: "tinder-pack"``.

Phase 3.5 — the 3 ``tinder_pack_*`` styles already live in
``data/styles.json`` (under ``mode: dating``) but didn't have the new
``scenario`` field. After this script they're hidden from the main
dating catalog and only surface through
``/api/v1/catalog/scenario-styles?scenario=tinder-pack``.

Idempotent::

    python scripts/tag_tinder_pack_scenario.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

TINDER_PACK_IDS = frozenset(
    {
        "tinder_pack_rooftop_golden",
        "tinder_pack_minimal_studio",
        "tinder_pack_cafe_window",
    }
)


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    tagged = 0
    missing = []

    for entry in styles:
        if entry.get("id") in TINDER_PACK_IDS:
            if entry.get("scenario") != "tinder-pack":
                entry["scenario"] = "tinder-pack"
                tagged += 1

    found_ids = {e["id"] for e in styles if e.get("id") in TINDER_PACK_IDS}
    missing = sorted(TINDER_PACK_IDS - found_ids)

    STYLES_PATH.write_text(
        json.dumps(styles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Tagged {tagged}/{len(TINDER_PACK_IDS)} tinder-pack styles")
    if missing:
        print(f"Warning — missing IDs: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
