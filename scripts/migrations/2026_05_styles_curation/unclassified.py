"""List the styles the heuristic could not classify.

Read-only diagnostic. Helps decide whether the loader-side
``_infer_location_type`` heuristic needs additional keyword
matches before we apply ``migrate.py`` to disk.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load_migrate():
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

    unclassified: list[tuple[str, str]] = []
    for s in styles:
        loc = mod._classify_location(s, doc_keys)
        if not loc:
            anchor = str(s.get("scene_anchor") or s.get("base_scene") or "").strip()
            unclassified.append((str(s.get("id") or ""), anchor[:90]))

    print(f"Unclassified styles: {len(unclassified)}\n")
    for sid, anchor in unclassified:
        print(f"  {sid:32s} | {anchor}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
