"""Diagnostic — print the current lint state of data/styles.json.

Usage: ``python -m scripts.migrations.2026_05_styles_curation.audit``

Read-only. Used to size the curation work before running the
``migrate.py`` companion script.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from src.services.style_lint import find_conflicts, lint_style


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    print(f"Total styles: {len(styles)}")

    lint_map = {s["id"]: lint_style(s) for s in styles}
    dirty = {k: v for k, v in lint_map.items() if v}
    codes: Counter[str] = Counter()
    for issues in dirty.values():
        for issue in issues:
            codes[issue["code"]] += 1

    print(f"Dirty styles: {len(dirty)}")
    print(f"Total issues: {sum(len(v) for v in dirty.values())}")
    print()
    print("By code:")
    for code, count in codes.most_common():
        print(f"  {code:22s} {count:4d}")
    print()

    available_set = sum(
        1 for s in styles if isinstance(s.get("available_channels"), list) and s["available_channels"]
    )
    location_set = sum(1 for s in styles if str(s.get("location_type") or "").strip())
    print(f"available_channels populated: {available_set} / {len(styles)}")
    print(f"location_type populated:     {location_set} / {len(styles)}")
    print()

    print("Top dirty styles (TRIGGER_DIRTY samples):")
    for sid, issues in list(dirty.items())[:15]:
        for i in issues:
            print(f"  {sid:30s} -> {i['code']:18s} field={i['field']:18s} {i['message'][:80]}")

    conflicts = find_conflicts(styles)
    print()
    print(f"Duplicate labels: {len(conflicts['duplicate_labels'])}")
    print(f"Similar labels:   {len(conflicts['similar_labels'])}")
    print(f"Duplicate IDs:    {len(conflicts['duplicate_ids'])}")
    if conflicts["duplicate_labels"]:
        print("  duplicate label samples:")
        for d in conflicts["duplicate_labels"][:5]:
            print(f"    {d['label']!r} -> {d['ids']}")
    if conflicts["similar_labels"]:
        print("  similar label samples:")
        for s in conflicts["similar_labels"][:5]:
            print(
                f"    [{s['distance']}] {s['label_a']!r} ({s['id_a']}) ~ "
                f"{s['label_b']!r} ({s['id_b']})"
            )


if __name__ == "__main__":
    main()
