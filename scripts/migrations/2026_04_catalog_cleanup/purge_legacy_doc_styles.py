"""One-shot migration: remove legacy doc styles and tag format styles.

Phase 3.1 of catalog cleanup:
- Drop 3 legacy document styles that duplicate the format-based ones.
- Tag the 5 remaining format styles with ``scenario: "document-photo"``
  so the main catalog filters them out and the document scenario page
  picks them up via ``/api/v1/catalog/scenario-styles``.

Usage::

    python scripts/purge_legacy_doc_styles.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

LEGACY_DOC_IDS = frozenset(
    {
        "doc_passport_neutral",
        "doc_visa_compliant",
        "doc_resume_headshot",
    }
)

DOCUMENT_FORMAT_IDS = frozenset(
    {
        "photo_3x4",
        "passport_rf",
        "visa_eu",
        "visa_us",
        "photo_4x6",
    }
)


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    before = len(styles)

    cleaned = [s for s in styles if s.get("id") not in LEGACY_DOC_IDS]
    removed = before - len(cleaned)

    tagged = 0
    for entry in cleaned:
        if entry.get("id") in DOCUMENT_FORMAT_IDS:
            if entry.get("scenario") != "document-photo":
                entry["scenario"] = "document-photo"
                tagged += 1

    STYLES_PATH.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Removed {removed} legacy doc styles "
        f"({before} -> {len(cleaned)}); tagged {tagged} format styles "
        "with scenario=document-photo"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
