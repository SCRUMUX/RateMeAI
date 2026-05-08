"""Generate ``data/landing_content.global.json`` with empty text fields.

Why:
    The global (EN) deployment historically read the RU-seeded copy of
    ``data/landing_content.json``, which surfaced Russian strings on
    ``ailookstudio.com``. The frontend parsers in
    ``web/src/lib/landing-cms.ts`` already use ``asString(...).trim() || fallback``,
    so blank CMS fields render the English copy from the i18n bundle.

What:
    This script walks every page and every block in the RU master file
    and produces a sibling file with the same shape but every text-like
    leaf replaced with an empty string. Numerical, boolean, ``visual``
    and any non-string fields are preserved so the layout (counters,
    enabled flags, image keys) stays intact.

Idempotent — re-running the script overwrites the global file with the
fresh skeleton derived from the current RU master.

Usage::

    python -m scripts.seed_landing_global
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RU_LANDING_PATH = REPO_ROOT / "data" / "landing_content.json"
GLOBAL_LANDING_PATH = REPO_ROOT / "data" / "landing_content.global.json"

# Block-level keys whose values should be passed through verbatim — they
# are either non-textual or carry layout-critical data (visual sources,
# counter base values, enabled flags). Everything else gets the empty
# string treatment when ``str``.
PRESERVED_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "type",
        "enabled",
        "visual",
        "icon",  # emoji glyph — language-neutral
        "base_count",
        "min_delay_ms",
        "max_delay_ms",
        "burst_chance",
        "max_burst_size",
        "ticker_interval_ms",
        "amount",
        "amount_currency",
        "currency",
        "pack_qty",
        "size_mm",
        "dpi",
        "background_color",
        "head_height_mm",
        "aspect_key",
    }
)


def _scrub(value: Any, key: str | None = None) -> Any:
    """Recursively replace string leaves with empty strings.

    Lists keep their length so the front-end iteration logic stays
    intact. Dicts keep their keys. ``PRESERVED_KEYS`` short-circuits the
    string clearing for layout/numeric metadata.
    """
    if key is not None and key in PRESERVED_KEYS:
        return value
    if isinstance(value, str):
        return ""
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, dict):
        return {k: _scrub(v, key=k) for k, v in value.items()}
    return value


def build_global_payload(ru_payload: dict[str, Any]) -> dict[str, Any]:
    pages = ru_payload.get("pages")
    if not isinstance(pages, dict):
        return {"pages": {}}

    cleaned_pages: dict[str, Any] = {}
    for slug, page in pages.items():
        if not isinstance(page, dict):
            continue
        blocks = page.get("blocks")
        cleaned_blocks: list[Any] = []
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    cleaned_blocks.append(block)
                    continue
                cleaned_block: dict[str, Any] = {}
                for k, v in block.items():
                    if k == "data" and isinstance(v, dict):
                        cleaned_block[k] = _scrub(v)
                    else:
                        cleaned_block[k] = _scrub(v, key=k)
                cleaned_blocks.append(cleaned_block)
        cleaned_pages[slug] = {**page, "blocks": cleaned_blocks}
    return {"pages": cleaned_pages}


def main() -> None:
    if not RU_LANDING_PATH.exists():
        raise SystemExit(f"RU landing file not found: {RU_LANDING_PATH}")
    raw = RU_LANDING_PATH.read_text(encoding="utf-8")
    ru_payload = json.loads(raw) if raw.strip() else {"pages": {}}
    if not isinstance(ru_payload, dict):
        raise SystemExit("RU landing file is not a JSON object")
    payload = build_global_payload(ru_payload)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    GLOBAL_LANDING_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {GLOBAL_LANDING_PATH} ({len(payload.get('pages', {}))} pages)")


if __name__ == "__main__":
    main()
