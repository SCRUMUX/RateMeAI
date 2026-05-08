"""Generate ``data/landing_content.global.json`` for the EN deployment.

Why:
    The global (EN) deployment historically read the RU-seeded copy of
    ``data/landing_content.json``, which surfaced Russian strings on
    ``ailookstudio.com``. The frontend parsers in
    ``web/src/lib/landing-cms.ts`` already use ``coalesceCmsString(...)``
    (1.58.0 hardening) so blank CMS fields render the English copy from
    the i18n bundle.

What:
    Two modes:

      * ``--mode=blank`` (default, legacy behavior) walks every page and
        every block in the RU master file and produces a sibling file
        with the same shape but every text-like leaf replaced with an
        empty string. Numerical, boolean, ``visual`` and any non-string
        fields are preserved so the layout (counters, enabled flags,
        image keys) stays intact.

      * ``--mode=auto-translate`` performs the same scrub *and then*
        seeds known fields from the EN i18n bundle
        (``web/src/locales/en/landing.json``) using ``LANDING_I18N_MAP``.
        This is 1.59.0 closure work: instead of relying purely on
        runtime fallbacks, we pre-fill the CMS so admin edits in
        ``/admin/landing`` start from the actual EN copy. Fields without
        a mapping stay blank and continue to use the i18n fallback.

Idempotent — both modes overwrite the global file with a fresh skeleton
derived from the current RU master. ``auto-translate`` re-seeds known
fields every run, but admin edits made *after* a seed are preserved
when ``--preserve-existing`` is passed: the script then keeps any
non-empty value already present in the global file and only fills in
fields that are still empty strings.

Usage::

    python -m scripts.seed_landing_global                   # blank skeleton
    python -m scripts.seed_landing_global --mode=auto-translate
    python -m scripts.seed_landing_global --mode=auto-translate --preserve-existing
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RU_LANDING_PATH = REPO_ROOT / "data" / "landing_content.json"
GLOBAL_LANDING_PATH = REPO_ROOT / "data" / "landing_content.global.json"
EN_BUNDLE_PATH = REPO_ROOT / "web" / "src" / "locales" / "en" / "landing.json"

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


# ---------------------------------------------------------------------------
# 1.59.0 — auto-translate mode.
# ---------------------------------------------------------------------------
# ``LANDING_I18N_MAP`` is keyed by ``(page_pattern, block_type)`` where
# ``page_pattern`` accepts globs (``*``, ``visa-*``) so we don't have to
# re-spell the visa fallback for every country. Field paths use dotted
# notation with ``[index]`` for arrays. The mapping resolves dotted i18n
# keys against ``web/src/locales/en/landing.json`` — keep this file
# authoritative, do not branch into other namespaces from here.
LANDING_I18N_MAP: dict[tuple[str, str], dict[str, str]] = {
    # ---- generic blocks (apply to every page that has them) -----------
    ("*", "footer"): {
        "brand.title": "footer.brandTitle",
        "brand.tagline": "footer.tagline",
        "creditsText": "footer.credits.text",
        "creditsLinkLabel": "footer.credits.linkLabel",
        "copyright": "footer.copyright",
    },
    ("*", "scenario_pricing"): {
        "tagline": "scenarioPricing.tagline",
    },
    # ---- home -----------------------------------------------------------
    ("home", "proof_counter"): {
        "heading": "proofCounter.heading",
        "subheading": "proofCounter.subheading",
    },
    ("home", "pricing"): {
        "title": "pricing.title",
        "subtitle": "pricing.subtitle",
        "caption": "pricing.caption",
        "tryFreeLabel": "pricing.tryFreeLabel",
        "plans[0].title": "pricing.plans.try.title",
        "plans[0].price": "pricing.plans.try.price",
        "plans[0].photos": "pricing.plans.try.photos",
        "plans[0].desc": "pricing.plans.try.desc",
        "plans[1].title": "pricing.plans.refresh.title",
        "plans[1].price": "pricing.plans.refresh.price",
        "plans[1].photos": "pricing.plans.refresh.photos",
        "plans[1].desc": "pricing.plans.refresh.desc",
        "plans[2].title": "pricing.plans.boost.title",
        "plans[2].price": "pricing.plans.boost.price",
        "plans[2].photos": "pricing.plans.boost.photos",
        "plans[2].desc": "pricing.plans.boost.desc",
        "plans[3].title": "pricing.plans.transform.title",
        "plans[3].price": "pricing.plans.transform.price",
        "plans[3].photos": "pricing.plans.transform.photos",
        "plans[3].desc": "pricing.plans.transform.desc",
    },
    # ---- document_photo -------------------------------------------------
    ("document_photo", "hero"): {
        "title": "documentPhoto.fallbackHero.title",
        "gradient_phrase": "documentPhoto.fallbackHero.gradientPhrase",
        "lead": "documentPhoto.fallbackHero.lead",
        "cta_label": "documentPhoto.fallbackHero.ctaLabel",
        "cta_microcopy": "documentPhoto.fallbackHero.ctaMicrocopy",
    },
    ("document_photo", "how_it_works"): {
        "title": "howItWorks.title",
        "steps[0].title": "howItWorks.step1Title",
        "steps[0].desc": "howItWorks.step1Desc",
        "steps[1].title": "howItWorks.step2Title",
        "steps[1].desc": "howItWorks.step2Desc",
        "steps[2].title": "howItWorks.step3Title",
        "steps[2].desc": "howItWorks.step3Desc",
    },
    # ---- visa-* (every country share these EN fallbacks) ----------------
    ("visa-*", "hero"): {
        "cta_label": "documentPhoto.fallbackHero.ctaLabel",
        "cta_microcopy": "documentPhoto.fallbackHero.ctaMicrocopy",
    },
    ("visa-*", "proof_counter"): {
        "heading": "visa.fallbackProof.heading",
        "subheading": "visa.fallbackProof.subheading",
    },
    ("visa-*", "how_it_works"): {
        "title": "visa.fallbackHow.title",
        "steps[0].title": "visa.fallbackHow.step1Title",
        "steps[0].desc": "visa.fallbackHow.step1Desc",
        "steps[1].title": "visa.fallbackHow.step2Title",
        "steps[1].desc": "visa.fallbackHow.step2Desc",
        "steps[2].title": "visa.fallbackHow.step3Title",
        "steps[2].desc": "visa.fallbackHow.step3Desc",
        "steps[3].title": "visa.fallbackHow.step4Title",
        "steps[3].desc": "visa.fallbackHow.step4Desc",
    },
    ("visa-*", "final_cta"): {
        "h2": "visa.fallbackFinal.h2",
        "lead": "visa.fallbackFinal.lead",
    },
    ("visa-*", "scenario_pricing"): {
        "tagline": "visa.fallbackPricing.tagline",
    },
}


_PATH_TOKEN_RE = re.compile(r"^([a-zA-Z0-9_]+)(?:\[(\d+)\])?$")


def _walk_dotted(target: dict[str, Any], path: str) -> tuple[Any, str | int] | None:
    """Resolve ``foo.bar[2].baz`` → (parent_container, last_key).

    Returns ``None`` if any intermediate node is missing; it is the
    caller's job to decide whether to skip or raise.
    """
    parts = path.split(".") if path else []
    if not parts:
        return None
    node: Any = target
    for idx, part in enumerate(parts):
        m = _PATH_TOKEN_RE.match(part)
        if not m:
            return None
        key = m.group(1)
        index = m.group(2)
        is_last = idx == len(parts) - 1
        if is_last:
            if index is None:
                if not isinstance(node, dict):
                    return None
                return node, key
            arr = node.get(key) if isinstance(node, dict) else None
            if not isinstance(arr, list):
                return None
            return arr, int(index)
        if index is None:
            child = node.get(key) if isinstance(node, dict) else None
            if child is None:
                return None
            node = child
            continue
        arr = node.get(key) if isinstance(node, dict) else None
        if not isinstance(arr, list) or int(index) >= len(arr):
            return None
        node = arr[int(index)]
    return None


def _read_i18n(bundle: dict[str, Any], dotted: str) -> str | None:
    """Resolve a dotted i18n key against the EN bundle."""
    parts = dotted.split(".")
    node: Any = bundle
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if isinstance(node, str) and node.strip():
        return node
    return None


def _matches_page(pattern: str, slug: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("-*"):
        return slug.startswith(pattern[:-1])
    return pattern == slug


def _apply_translation(
    block_data: dict[str, Any],
    field_path: str,
    value: str,
    *,
    preserve_existing: bool,
) -> bool:
    """Set ``field_path`` inside ``block_data`` to ``value`` if appropriate.

    Returns ``True`` if a write happened, ``False`` if skipped (missing
    path or preserved existing).
    """
    target = _walk_dotted(block_data, field_path)
    if target is None:
        return False
    container, key = target
    if isinstance(container, list) and isinstance(key, int):
        if key >= len(container):
            return False
        current = container[key]
        if preserve_existing and isinstance(current, str) and current.strip():
            return False
        container[key] = value
        return True
    if isinstance(container, dict):
        current = container.get(key)
        if preserve_existing and isinstance(current, str) and current.strip():
            return False
        container[key] = value
        return True
    return False


def auto_translate(payload: dict[str, Any], *, preserve_existing: bool) -> dict[str, Any]:
    """Seed known CMS fields from the EN i18n bundle."""
    if not EN_BUNDLE_PATH.exists():
        raise SystemExit(f"EN landing bundle not found: {EN_BUNDLE_PATH}")
    bundle = json.loads(EN_BUNDLE_PATH.read_text(encoding="utf-8"))
    pages = payload.get("pages")
    if not isinstance(pages, dict):
        return payload

    written = 0
    skipped = 0
    for slug, page in pages.items():
        if not isinstance(page, dict):
            continue
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            data = block.get("data")
            if not isinstance(block_type, str) or not isinstance(data, dict):
                continue
            for (page_pattern, btype), mapping in LANDING_I18N_MAP.items():
                if btype != block_type:
                    continue
                if not _matches_page(page_pattern, slug):
                    continue
                for field_path, i18n_key in mapping.items():
                    translated = _read_i18n(bundle, i18n_key)
                    if translated is None:
                        skipped += 1
                        continue
                    if _apply_translation(
                        data, field_path, translated, preserve_existing=preserve_existing
                    ):
                        written += 1
                    else:
                        skipped += 1
    print(f"auto-translate: {written} fields written, {skipped} skipped")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--mode",
        choices=("blank", "auto-translate"),
        default="blank",
        help="`blank` = scrub all strings to ''. `auto-translate` = also "
        "seed known fields from web/src/locales/en/landing.json.",
    )
    parser.add_argument(
        "--preserve-existing",
        action="store_true",
        help="When auto-translating an existing global file, do not "
        "overwrite fields that already contain non-empty strings.",
    )
    args = parser.parse_args()

    if not RU_LANDING_PATH.exists():
        raise SystemExit(f"RU landing file not found: {RU_LANDING_PATH}")
    raw = RU_LANDING_PATH.read_text(encoding="utf-8")
    ru_payload = json.loads(raw) if raw.strip() else {"pages": {}}
    if not isinstance(ru_payload, dict):
        raise SystemExit("RU landing file is not a JSON object")
    payload = build_global_payload(ru_payload)

    if args.mode == "auto-translate":
        # When ``--preserve-existing`` is set, blend in the values from
        # the previous global file so admin edits are kept on a re-seed.
        if args.preserve_existing and GLOBAL_LANDING_PATH.exists():
            try:
                prev = json.loads(GLOBAL_LANDING_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                prev = None
            if isinstance(prev, dict) and isinstance(prev.get("pages"), dict):
                payload = _merge_existing(payload, prev)
        payload = auto_translate(payload, preserve_existing=args.preserve_existing)

    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    GLOBAL_LANDING_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {GLOBAL_LANDING_PATH} ({len(payload.get('pages', {}))} pages)")


def _merge_existing(fresh: dict[str, Any], prev: dict[str, Any]) -> dict[str, Any]:
    """Bring forward non-empty leaves from ``prev`` into ``fresh``.

    Used by ``--preserve-existing`` so admin tweaks made in
    ``/admin/landing`` survive the re-seed. We only copy strings that
    are non-empty; everything else is taken from the freshly-scrubbed
    skeleton (which already has structure parity with the RU master).
    """

    def _merge_node(a: Any, b: Any) -> Any:
        if isinstance(a, dict) and isinstance(b, dict):
            for k, v in a.items():
                if k in b:
                    a[k] = _merge_node(v, b[k])
            return a
        if isinstance(a, list) and isinstance(b, list):
            for i in range(min(len(a), len(b))):
                a[i] = _merge_node(a[i], b[i])
            return a
        if isinstance(a, str) and isinstance(b, str) and b.strip():
            return b
        return a

    return _merge_node(fresh, prev)  # type: ignore[no-any-return]


if __name__ == "__main__":
    main()
