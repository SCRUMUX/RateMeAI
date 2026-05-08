"""Audit i18n coverage for the style catalog.

1.59.0 — diff ``data/styles.json`` (the master catalog used by the
backend `/api/v1/catalog/styles` endpoint) against
``web/src/locales/{ru,en}/styles.json`` (the SPA i18n bundles
consumed by ``localizeApiStyle`` and ``LANDING_STYLES_BY_CATEGORY``).

The script exits 0 on a clean diff and 1 when any catalog id is
missing from the bundle so it can be wired into CI later. Run it
manually any time a new style ships:

    python -m scripts.audit_styles

It prints two tables — RU coverage and EN coverage — and the list of
keys present in the bundle but no longer in the catalog (orphan keys
to clean up).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "styles.json"
LOCALE_PATHS = {
    "ru": ROOT / "web" / "src" / "locales" / "ru" / "styles.json",
    "en": ROOT / "web" / "src" / "locales" / "en" / "styles.json",
}


def _load_catalog() -> list[dict]:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_locale(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _catalog_keys_by_category(catalog: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for entry in catalog:
        style_id = entry.get("id")
        mode = entry.get("mode") or "social"
        if not style_id or not isinstance(mode, str):
            continue
        # Document and visa styles are scenario-only and may be tagged
        # with mode='cv', but we keep them under the ``documents``
        # i18n bucket where the EN copy lives. Treat the
        # ``is_scenario_only`` + scenario tag as the deciding factor.
        scenario_tag = (entry.get("scenario") or entry.get("scenario_slug") or "").lower()
        if scenario_tag.startswith("document") or scenario_tag.startswith("visa"):
            bucket = "documents"
        else:
            bucket = mode
        out.setdefault(bucket, set()).add(style_id)
    return out


def _locale_keys_by_category(locale: dict) -> dict[str, set[str]]:
    return {
        cat: {key for key in items.keys()}
        for cat, items in locale.items()
        if isinstance(items, dict)
    }


def _format_section(header: str, items: Iterable[str]) -> str:
    items = sorted(items)
    if not items:
        return f"{header}: ✓ none"
    return f"{header}: {len(items)}\n  - " + "\n  - ".join(items)


def main() -> int:
    catalog = _load_catalog()
    catalog_keys = _catalog_keys_by_category(catalog)

    exit_code = 0
    print(f"Catalog: {CATALOG_PATH.relative_to(ROOT)} ({sum(len(v) for v in catalog_keys.values())} styles)")
    print()

    for lang, path in LOCALE_PATHS.items():
        locale = _load_locale(path)
        locale_keys = _locale_keys_by_category(locale)
        print(f"=== {lang.upper()} bundle: {path.relative_to(ROOT)} ===")

        all_missing: list[str] = []
        all_orphans: list[str] = []

        all_categories = sorted(set(catalog_keys.keys()) | set(locale_keys.keys()))
        for cat in all_categories:
            in_catalog = catalog_keys.get(cat, set())
            in_locale = locale_keys.get(cat, set())
            missing = sorted(in_catalog - in_locale)
            orphans = sorted(in_locale - in_catalog)
            if missing or orphans:
                print(f"\n[{cat}] catalog={len(in_catalog)} locale={len(in_locale)}")
                if missing:
                    all_missing.extend(f"{cat}.{k}" for k in missing)
                    print(_format_section("  MISSING (catalog -> locale)", missing))
                if orphans:
                    all_orphans.extend(f"{cat}.{k}" for k in orphans)
                    print(_format_section("  ORPHAN (locale, not in catalog)", orphans))

        if all_missing:
            exit_code = 1
        print()
        print(f"  Total missing: {len(all_missing)}, orphans: {len(all_orphans)}")
        print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
