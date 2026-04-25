"""One-shot: replace emoji prefixes in display_label to break duplicates.

Catalog audit found same emoji used by multiple styles in the same mode
(e.g. ☕ for `coffee_date`, `night_coffee`, `cafe`). UX needs each row
in the picker to be visually distinct, so we re-pick emojis per the
plan (`Catalog Cleanup And Admin`, фаза 1.2).

Run::

    python scripts/rename_style_emojis.py
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover — defensive for older interpreters
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

EMOJI_RENAMES: dict[str, str] = {
    # dating
    "coffee_date": "🥐",
    "night_coffee": "🌙",
    "cafe": "☕",
    "car_exit": "🚪",
    "near_car": "🚗",
    "airplane_window": "🛫",
    "travel": "✈️",
    "nyc_brooklyn_bridge": "🌉",
    "sf_golden_gate": "🌁",
    "rome_colosseum": "🏛",
    "athens_acropolis": "🏺",
    "art_gallery": "🎨",
    # cv
    "formal_portrait": "📷",
    "neutral": "🎯",
    "tablet_stylus": "📱",
    "between_meetings": "📲",
    "startup_casual": "🚀",
    "entrepreneur_on_move": "🌱",
    # social
    "morning_routine": "🌅",
    "casual": "☀️",
    "vintage_film": "🎞",
    "photographer": "📷",
    "yoga_social": "🪷",
}


_LEADING_EMOJI = re.compile(r"^[^\w\sА-Яа-яЁё]+\s*")


def replace_prefix(label: str, new_emoji: str) -> str:
    stripped = _LEADING_EMOJI.sub("", label).strip()
    return f"{new_emoji} {stripped}".strip()


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    updated = 0
    missing: list[str] = []
    seen: set[str] = set()

    for entry in styles:
        sid = entry.get("id")
        if sid in EMOJI_RENAMES:
            seen.add(sid)
            old = entry.get("display_label", "")
            new = replace_prefix(old, EMOJI_RENAMES[sid])
            if old != new:
                entry["display_label"] = new
                updated += 1
                print(f"  {sid}: {old!r} -> {new!r}")

    for sid in EMOJI_RENAMES:
        if sid not in seen:
            missing.append(sid)

    STYLES_PATH.write_text(
        json.dumps(styles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\nUpdated {updated} labels.")
    if missing:
        print(f"WARNING: {len(missing)} target ids not present in styles.json:")
        for sid in missing:
            print(f"  - {sid}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
