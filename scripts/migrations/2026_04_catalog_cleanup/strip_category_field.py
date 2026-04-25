"""One-shot migration: strip the dead ``category`` field from styles.json.

Every entry currently has ``"category": "General"``. Nothing in the
runtime reads it (UI groups by it but always sees a single bucket;
catalog API only echoes it back). Removing it now keeps the file
honest and shrinks the diff for future style edits.

Usage::

    python scripts/strip_category_field.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    removed = 0
    for entry in styles:
        if "category" in entry:
            entry.pop("category")
            removed += 1

    STYLES_PATH.write_text(
        json.dumps(styles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Removed 'category' from {removed}/{len(styles)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
