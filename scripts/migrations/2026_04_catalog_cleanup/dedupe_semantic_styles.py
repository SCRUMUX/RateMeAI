"""One-shot migration: drop semantic duplicates from ``data/styles.json``.

Phase 4 of the catalog cleanup. After Phase 3 the catalog has 138
entries; manual review uncovered 11 semantic duplicates (4 CV + 7
social) that share intent and target metric with a kept twin. Removing
them brings the catalog down to **127** clean styles.

The script is purely subtractive — it does not rewrite or merge the
remaining entries. Re-running is a no-op.

Usage::

    python scripts/dedupe_semantic_styles.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

# (deleted_id -> kept_id) — the kept twin is documented next to the
# deletion so future readers can quickly verify the dedupe decision.
DUPLICATES: dict[str, str] = {
    # CV
    "creative": "creative_director",
    "between_meetings": "before_meeting",
    "man_with_mission": "decision_moment",
    "entrepreneur_on_move": "decision_moment",
    "quiet_expert": "intellectual",
    # Social
    "influencer": "influencer_urban",
    "influencer_luxury": "luxury",
    "book_and_coffee": "reading_home",
    "creative_insight": "artistic",
    "creative_portrait": "artistic",
    "dark_moody": "focused_mood",
    "yoga_social": "meditation",
}


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in styles}

    missing_keepers = [keep for keep in DUPLICATES.values() if keep not in by_id]
    if missing_keepers:
        unique_missing = sorted(set(missing_keepers))
        print(f"ERROR — kept twins not found in styles.json: {unique_missing}")
        return 1

    before = len(styles)
    cleaned = [s for s in styles if s.get("id") not in DUPLICATES]
    removed = before - len(cleaned)

    STYLES_PATH.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Removed {removed}/{len(DUPLICATES)} semantic duplicates "
        f"({before} -> {len(cleaned)} styles)."
    )
    not_present = [d for d in DUPLICATES if d not in by_id]
    if not_present:
        print(f"Note — already absent (idempotent run): {sorted(not_present)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
