"""One-shot migration: seed ``unlock_after_generations`` on premium styles.

Phase 2 of the catalog tech-debt cleanup. After the FNV-fallback was
removed from the frontend lock logic, the lock UI became inert because
no entry in ``data/styles.json`` had ``unlock_after_generations >= 1``.
This script restores intent by tagging 10 hand-picked "wow"-effect
styles with a 3-or-5-generation unlock threshold so the locked-state
badge in :file:`web/src/components/wizard/StylesSheet.tsx` lights up
again for fresh users.

Selection rationale (matches plan §2.1):

* dating: city-trip / luxury-travel anchors
* cv: high-status / on-stage moments
* social: cinematic vibe shots

The script is idempotent and *additive* — it only writes the field if
the value changes, and never touches other style attributes. Re-running
is a no-op.

Usage::

    python scripts/seed_premium_unlocks.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

# (style_id -> threshold). Sources of "premium" intent:
# - 5: ultra-aspirational visuals (luxury / iconic / executive moments)
# - 3: lighter premium (city-flagship / cinematic-mood) reachable sooner
PREMIUM_UNLOCKS: dict[str, int] = {
    # dating — landmarks & travel-luxury
    "dubai_burj_khalifa": 5,
    "yacht": 5,
    "travel_luxury": 5,
    "nyc_times_square": 3,
    # cv — high-status / on-stage
    "business_lounge": 5,
    "speaker_stage": 5,
    "decision_moment": 3,
    # social — cinematic / wow-effect
    "skyscraper_view": 5,
    "golden_hour": 3,
    "neon_night": 3,
}


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in styles}

    missing = sorted(set(PREMIUM_UNLOCKS) - set(by_id))
    if missing:
        print(f"ERROR — premium IDs not found in styles.json: {missing}")
        return 1

    changed = 0
    skipped_already = 0
    for sid, threshold in PREMIUM_UNLOCKS.items():
        entry = by_id[sid]
        current = int(entry.get("unlock_after_generations") or 0)
        if current == threshold:
            skipped_already += 1
            continue
        entry["unlock_after_generations"] = threshold
        changed += 1
        print(f"  set unlock_after_generations={threshold} on {sid} (was {current})")

    if changed == 0:
        print(f"No-op: all {skipped_already} premium styles already at target.")
        return 0

    STYLES_PATH.write_text(
        json.dumps(styles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Updated {changed} style(s) "
        f"({skipped_already} were already at target). Wrote {STYLES_PATH}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
