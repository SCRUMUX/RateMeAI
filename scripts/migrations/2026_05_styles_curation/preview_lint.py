"""Preview lint state after running migrate.py in memory.

Read-only — neither the source file nor any cache is touched.
Used to verify that the migration would actually clear the
issues before we commit to writing to disk.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from src.services.style_lint import lint_style


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load_migrate():
    # Imported lazily because the module name starts with a digit and
    # Python can't import it via the dotted form. We re-execute it in
    # an isolated namespace so it's available here.
    import importlib.util

    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(
        "_curation_migrate", here / "migrate.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load_migrate()
    raw = STYLES_PATH.read_text(encoding="utf-8")
    styles = json.loads(raw)
    doc_keys = mod._document_keys()
    new_styles = [mod._apply(e, doc_keys)[0] for e in styles]

    before_dirty = {s["id"]: lint_style(s) for s in styles}
    after_dirty = {s["id"]: lint_style(s) for s in new_styles}

    before_dirty = {k: v for k, v in before_dirty.items() if v}
    after_dirty = {k: v for k, v in after_dirty.items() if v}

    before_codes: Counter[str] = Counter()
    after_codes: Counter[str] = Counter()
    for issues in before_dirty.values():
        for i in issues:
            before_codes[i["code"]] += 1
    for issues in after_dirty.values():
        for i in issues:
            after_codes[i["code"]] += 1

    print(f"Before — dirty styles: {len(before_dirty)}, total issues: {sum(before_codes.values())}")
    for code, n in before_codes.most_common():
        print(f"  {code:22s} {n}")
    print()
    print(f"After  — dirty styles: {len(after_dirty)}, total issues: {sum(after_codes.values())}")
    for code, n in after_codes.most_common():
        print(f"  {code:22s} {n}")
    print()

    if after_dirty:
        print("Remaining dirty styles after migration:")
        for sid, issues in sorted(after_dirty.items()):
            for i in issues:
                print(f"  {sid:32s} {i['code']:22s} {i['message'][:90]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
