"""Bulk curation pass for ``data/styles.json`` (1.30.0).

Closes the loop opened by 1.29.0: the admin UI is now in place but
0/126 styles have ``available_channels`` or ``location_type`` set.
This script applies the same heuristics the operator would click
through manually, in one deterministic pass:

1. **location_type** — auto-derived from ``scene_anchor`` keywords.
   Document styles (passport / visa / driver license / id photos)
   force ``"document"``; everything else falls into ``indoor`` /
   ``outdoor`` / ``mixed`` / ``""`` (unclassified).

2. **available_channels** — derived from ``location_type``:

     | location_type | channels enabled                                  |
     |---------------|---------------------------------------------------|
     | document      | (none — fully locked)                             |
     | indoor        | lighting, time_of_day, framing, clothing,         |
     |               | scene_override                                    |
     | outdoor       | lighting, weather, time_of_day, season,           |
     |               | framing, clothing, scene_override                 |
     | mixed         | lighting, time_of_day, framing, clothing,         |
     |               | scene_override (no weather/season — ambiguous)    |
     | "" (empty)    | (none — leave uncurated, legacy fallback kicks in)|

   Ambient channels are only enabled when the corresponding pool is
   non-empty (otherwise ``EMPTY_POOL`` lint error). When ``season``
   would land in the channel list but its pool has fewer than 4
   seasons, the script fills it with ``[spring, summer, autumn, winter]``.

3. **trigger_pool cleanup** — for every entry that contains a
   framing / lighting / weather / season token (per the lint
   engine's blocklists), drop it from the pool **iff** there is at
   least one clean alternative left. Single-phrase pools are kept
   as-is so we never reduce trigger semantics — those styles get a
   ``TRIGGER_DIRTY`` warning that the operator can later resolve
   in the admin UI.

The script accepts a ``--dry-run`` flag that prints the diff
summary without writing the file.

Idempotent: re-running on an already-curated file is a no-op
(modulo whitespace), because every step computes the desired
state from the current ``scene_anchor`` / pool contents and
the inputs are deterministic functions of those.

Usage::

    # Dry-run, show diff summary
    python -m scripts.migrations.2026_05_styles_curation.migrate --dry-run

    # Apply
    python -m scripts.migrations.2026_05_styles_curation.migrate

The script lives next to ``audit.py`` (read-only diagnostic) and
its outputs feed back into the same lint engine the admin UI
uses, so a clean run here is exactly equivalent to "operator
clicked save on every style with the recommended defaults".
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from src.prompts.style_schema_v3 import (
    CHANNEL_CLOTHING,
    CHANNEL_FRAMING,
    CHANNEL_LIGHTING,
    CHANNEL_SCENE_OVERRIDE,
    CHANNEL_SEASON,
    CHANNEL_TIME_OF_DAY,
    CHANNEL_WEATHER,
    LOCATION_TYPE_DOCUMENT,
    LOCATION_TYPE_INDOOR,
    LOCATION_TYPE_MIXED,
    LOCATION_TYPE_OUTDOOR,
)
from src.services.style_lint import (
    _FRAMING_TOKENS,
    _LIGHTING_TOKENS,
    _SEASON_TOKENS,
    _WEATHER_TOKENS,
)
from src.services.style_loader_v3 import _infer_location_type


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

# Force UTF-8 stdout so emoji-heavy display labels in the diff
# preview don't crash on Windows cp1251 consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Document styles share their key with the runtime detector. We
# import here lazily because ``style_spec`` pulls the entire spec
# graph; the import cost matters for the dry-run path.
def _document_keys() -> frozenset[str]:
    from src.prompts.style_spec import _DOCUMENT_STYLE_KEYS

    return _DOCUMENT_STYLE_KEYS


# Per-location channel template. Order matters — the admin UI
# renders channels in this order and the JSON-on-disk diff is
# easier to scan when the order is stable.
_CHANNELS_BY_LOCATION: dict[str, tuple[str, ...]] = {
    LOCATION_TYPE_DOCUMENT: (),
    LOCATION_TYPE_INDOOR: (
        CHANNEL_LIGHTING,
        CHANNEL_TIME_OF_DAY,
        CHANNEL_FRAMING,
        CHANNEL_CLOTHING,
        CHANNEL_SCENE_OVERRIDE,
    ),
    LOCATION_TYPE_OUTDOOR: (
        CHANNEL_LIGHTING,
        CHANNEL_WEATHER,
        CHANNEL_TIME_OF_DAY,
        CHANNEL_SEASON,
        CHANNEL_FRAMING,
        CHANNEL_CLOTHING,
        CHANNEL_SCENE_OVERRIDE,
    ),
    LOCATION_TYPE_MIXED: (
        CHANNEL_LIGHTING,
        CHANNEL_TIME_OF_DAY,
        CHANNEL_FRAMING,
        CHANNEL_CLOTHING,
        CHANNEL_SCENE_OVERRIDE,
    ),
}


# Channels whose enable-state must be backed by a non-empty
# ambient pool, otherwise the lint engine raises ``EMPTY_POOL``.
_AMBIENT_BACKED: frozenset[str] = frozenset(
    {CHANNEL_LIGHTING, CHANNEL_WEATHER, CHANNEL_TIME_OF_DAY, CHANNEL_SEASON}
)


_REQUIRED_SEASONS: tuple[str, ...] = ("spring", "summer", "autumn", "winter")


_TRIGGER_DIRTY_TOKENS: tuple[str, ...] = tuple(
    set(_FRAMING_TOKENS + _LIGHTING_TOKENS + _WEATHER_TOKENS + _SEASON_TOKENS)
)


def _trigger_is_dirty(phrase: str) -> bool:
    haystack = phrase.lower()
    return any(tok in haystack for tok in _TRIGGER_DIRTY_TOKENS)


def _classify_location(entry: dict[str, Any], doc_keys: frozenset[str]) -> str:
    """Compute a final ``location_type`` for the entry.

    Existing non-empty value wins (idempotency). Otherwise we
    delegate to the same heuristic the loader uses, with the
    document override applied first.
    """
    explicit = str(entry.get("location_type") or "").strip().lower()
    if explicit:
        return explicit
    sid = str(entry.get("id") or "")
    if sid in doc_keys:
        return LOCATION_TYPE_DOCUMENT
    anchor = str(entry.get("scene_anchor") or entry.get("base_scene") or "").strip()
    return _infer_location_type(anchor, sid)


def _ambient_pool(entry: dict[str, Any], channel: str) -> list[str]:
    ambient = entry.get("ambient")
    if not isinstance(ambient, dict):
        return []
    pool = ambient.get(channel)
    if not isinstance(pool, list):
        return []
    return [p for p in pool if isinstance(p, str) and p.strip()]


def _compute_channels(
    entry: dict[str, Any], location_type: str
) -> tuple[list[str], dict[str, list[str]]]:
    """Pick the ``available_channels`` list and any pool patches.

    Returns ``(channels, pool_patches)`` where ``pool_patches`` is a
    dict of channel → new pool contents to merge into ``ambient``.
    The patches cover the "fill 4 seasons when season is enabled"
    rule and only contain channels we are explicitly populating.
    """
    template = _CHANNELS_BY_LOCATION.get(location_type, ())
    selected: list[str] = []
    patches: dict[str, list[str]] = {}

    for ch in template:
        if ch in _AMBIENT_BACKED:
            pool = _ambient_pool(entry, ch)
            if ch == CHANNEL_SEASON and pool:
                # Keep the channel only if pool is non-empty; if it
                # has 1-3 entries we expand to the canonical four
                # so the lint warning clears.
                merged = list(_REQUIRED_SEASONS)
                if merged != pool:
                    patches[CHANNEL_SEASON] = merged
                selected.append(ch)
                continue
            if ch == CHANNEL_SEASON and not pool:
                # No season values authored. We could fill with the
                # default four — the user explicitly asked for "4
                # сезона по умолчанию". Do that for outdoor styles.
                patches[CHANNEL_SEASON] = list(_REQUIRED_SEASONS)
                selected.append(ch)
                continue
            if pool:
                selected.append(ch)
            # else: drop the channel rather than emit EMPTY_POOL.
        else:
            selected.append(ch)

    return selected, patches


def _clean_trigger_pool(pool: list[str]) -> tuple[list[str], list[str]]:
    """Drop dirty phrases when alternatives exist.

    Single-phrase pools are returned untouched (we never reduce
    trigger semantics to nothing — the operator handles those via
    the admin UI). Pools with multiple phrases shed every entry
    that contains a framing / lighting / weather / season token,
    falling back to the original pool if cleanup would empty it.
    """
    if len(pool) <= 1:
        return list(pool), []
    clean = [p for p in pool if not _trigger_is_dirty(p)]
    if not clean:
        return list(pool), []
    removed = [p for p in pool if _trigger_is_dirty(p)]
    return clean, removed


def _apply(
    entry: dict[str, Any], doc_keys: frozenset[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute the curated entry + a per-style change record."""
    out = dict(entry)
    changes: dict[str, Any] = {}

    new_location = _classify_location(entry, doc_keys)
    old_location = str(entry.get("location_type") or "").strip().lower()
    if new_location != old_location:
        out["location_type"] = new_location
        changes["location_type"] = (old_location or None, new_location)

    channels, pool_patches = _compute_channels(out, new_location)
    old_channels = (
        list(entry.get("available_channels") or [])
        if isinstance(entry.get("available_channels"), list)
        else []
    )
    if channels != old_channels:
        out["available_channels"] = channels
        changes["available_channels"] = (old_channels, channels)

    if pool_patches:
        ambient = dict(out.get("ambient") or {})
        for ch, new_pool in pool_patches.items():
            old_pool = ambient.get(ch) if isinstance(ambient.get(ch), list) else []
            if list(old_pool) != new_pool:
                ambient[ch] = new_pool
                changes.setdefault("ambient_patches", {})[ch] = (
                    list(old_pool),
                    new_pool,
                )
        out["ambient"] = ambient

    pool = (
        list(entry.get("trigger_pool") or [])
        if isinstance(entry.get("trigger_pool"), list)
        else []
    )
    if pool:
        cleaned, removed = _clean_trigger_pool(pool)
        if cleaned != pool:
            out["trigger_pool"] = cleaned
            changes["trigger_pool_removed"] = removed

    return out, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diff summary without writing the file.",
    )
    args = parser.parse_args()

    raw = STYLES_PATH.read_text(encoding="utf-8")
    styles = json.loads(raw)
    doc_keys = _document_keys()

    new_styles: list[dict[str, Any]] = []
    changes_per_style: dict[str, dict[str, Any]] = {}
    location_counter: Counter[str] = Counter()
    channels_counter: Counter[str] = Counter()
    triggers_removed_total = 0

    for entry in styles:
        new_entry, changes = _apply(entry, doc_keys)
        new_styles.append(new_entry)
        if changes:
            changes_per_style[str(entry.get("id"))] = changes
        location_counter[str(new_entry.get("location_type") or "")] += 1
        for ch in new_entry.get("available_channels") or []:
            channels_counter[str(ch)] += 1
        if "trigger_pool_removed" in changes:
            triggers_removed_total += len(changes["trigger_pool_removed"])

    print(f"Total styles processed: {len(styles)}")
    print(f"Styles changed:         {len(changes_per_style)}")
    print()
    print("Location distribution after migration:")
    for loc, n in sorted(location_counter.items(), key=lambda kv: -kv[1]):
        label = loc or "(unclassified)"
        print(f"  {label:18s} {n:4d}")
    print()
    print("Channel adoption (across all styles):")
    for ch, n in sorted(channels_counter.items(), key=lambda kv: -kv[1]):
        print(f"  {ch:18s} {n:4d}")
    print()
    print(f"Trigger phrases removed (with safe fallback): {triggers_removed_total}")

    sample = list(changes_per_style.items())[:10]
    if sample:
        print()
        print("Sample diff (first 10 changed styles):")
        for sid, ch in sample:
            line_parts = []
            if "location_type" in ch:
                old, new = ch["location_type"]
                line_parts.append(f"loc={old or '∅'}→{new}")
            if "available_channels" in ch:
                _, new = ch["available_channels"]
                line_parts.append(f"ch={len(new)}")
            if "ambient_patches" in ch:
                line_parts.append(
                    f"pools={list(ch['ambient_patches'].keys())}"
                )
            if "trigger_pool_removed" in ch:
                line_parts.append(
                    f"trig-removed={len(ch['trigger_pool_removed'])}"
                )
            print(f"  {sid:32s} {' '.join(line_parts)}")

    if args.dry_run:
        print()
        print("[dry-run] no file written")
        return 0

    STYLES_PATH.write_text(
        json.dumps(new_styles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"[applied] wrote {STYLES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
