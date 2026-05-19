"""Scan ``data/styles.json`` with the v1.66 lint rules.

Read-only: prints a per-code count of remaining issues and lists any
style that still trips ``EXPRESSION_PORTRAIT_LEAK`` / ``SCENE_POSE_LEAK``
/ ``WARDROBE_TIGHT_SUIT`` after the v1.66 migration ran. Used by the
deploy checklist to confirm the catalog is clean before committing.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from src.services.style_lint import lint_style  # noqa: E402


V166_CODES = ("EXPRESSION_PORTRAIT_LEAK", "SCENE_POSE_LEAK", "WARDROBE_TIGHT_SUIT")


def main() -> int:
    styles_path = REPO_ROOT / "data" / "styles.json"
    styles = json.loads(styles_path.read_text(encoding="utf-8"))

    codes: Counter[str] = Counter()
    dirty: dict[str, list] = {}
    for entry in styles:
        if not isinstance(entry, dict):
            continue
        issues = lint_style(entry)
        if not issues:
            continue
        sid = str(entry.get("id") or "")
        dirty[sid] = issues
        for issue in issues:
            codes[issue["code"]] += 1

    print(f"Dirty styles: {len(dirty)}, total issues: {sum(codes.values())}")
    for code, n in codes.most_common():
        print(f"  {code:30s} {n}")

    print()
    print("v1.66 rules — remaining hits:")
    v166_hits = 0
    for sid, issues in sorted(dirty.items()):
        for issue in issues:
            if issue["code"] in V166_CODES:
                v166_hits += 1
                print(f"  {sid:32s} {issue['code']:24s} {issue['message'][:90]}")
    if not v166_hits:
        print("  (none — catalog is clean for v1.66 rules)")

    return 0 if not v166_hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
