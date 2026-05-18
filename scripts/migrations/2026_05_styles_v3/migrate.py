"""Stage 2 migration: rewrite ``data/styles.json`` into StyleSpecV3 shape.

Part of the prompt-pipeline-overhaul (2026-05). For every entry in the
catalog the script:

* Auto-derives v3 fields from the existing v2 payload:

  - ``scene_anchor`` — ``base_scene`` (or ``background.base``) with all
    lighting / weather / time-of-day / season tokens stripped out,
    using a small phrase-level cleaner backed by the ``LIGHTING_KW``
    regex from :mod:`audit_v2_styles`.
  - ``trigger_pool`` — when curated, the curated phrasings; otherwise
    a single-element pool ``[scene_anchor]`` so the headline motif
    (the landmark or interior already in the scene anchor) is always
    materialised by :mod:`src.prompts.slot_sampler`.
  - ``ambient.lighting`` — entries from ``context_slots.lighting``
    classified as pure-lighting by :func:`classify_lighting_entry`,
    plus any curated overrides.
  - ``ambient.weather`` — ``weather.allowed`` when ``weather.enabled``,
    plus any curated overrides.
  - ``ambient.time_of_day`` — heuristically extracted from the lighting
    pool (``"morning"``, ``"golden hour"``, ``"blue hour"``, ...) when
    not curated.
  - ``ambient.season`` — empty unless curated.
  - ``scene_overrides`` — ``background.overrides_allowed`` (already
    populated by Phase 2 of the v1.27.2 cleanup), plus curated entries.
  - ``background_lock`` — copied from ``background.lock`` unless
    curated.

* Merges any per-style overrides from ``curated.json`` over the auto
  derivation. The curated file is the editable surface for top
  styles where the auto-stripped scene_anchor is too coarse or where
  trigger phrasings deserve manual diversity (5+ variants per
  trigger pool to maximise compositional variety across users).

* Sets ``schema_version: 3`` for every successfully migrated style and
  preserves every legacy v2 field (``base_scene``, ``allowed_variations``,
  ``trigger``, ``background``, ``context_slots``, ``weather``, ...) so
  the v2 loader keeps working for all consumers that have not opted
  into v3 yet.

* Skips entries whose auto-derived ``trigger_pool`` is empty and they
  carry no usable ``trigger`` / ``base_scene`` — those rows stay at
  ``schema_version: 2`` (and surface in the run summary so the human
  curator can fill ``curated.json``).

The script is idempotent: re-running on a v3 file refreshes the
auto-derived fields without touching curated overrides. Use
``--dry-run`` to preview the diff and ``--keys foo bar`` to scope the
run to specific style ids during incremental curation.

Usage::

    python scripts/migrations/2026_05_styles_v3/migrate.py
    python scripts/migrations/2026_05_styles_v3/migrate.py --dry-run
    python scripts/migrations/2026_05_styles_v3/migrate.py --keys mirror_aesthetic dubai_burj_khalifa
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
CURATED_PATH = Path(__file__).resolve().parent / "curated.json"

# Reuse the audit's lighting-vs-location classifier so we don't drift
# from Phase-2 heuristics. ``audit_v2_styles`` lives next door.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "migrations" / "2026_04_prompt_quality"))
from audit_v2_styles import classify_lighting_entry  # noqa: E402


# --- Phrase-level cleaners ------------------------------------------------

# Inline lighting phrases that get stripped from scene_anchor when they
# appear as a trailing modifier inside a fragment (e.g.
# "with Burj Khalifa landmark illuminated at blue hour"). Keeping the
# list focused on patterns we observed in v2 base_scene strings — adding
# more is safe (only narrows scene_anchor, never widens it).
_INLINE_LIGHTING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\s+(?:illuminated|lit|bathed|wrapped)\s+(?:at|by|in|with)\s+"
        r"(?:blue\s+hour|golden\s+hour|sunset|sunrise|night|dawn|dusk|"
        r"morning(?:\s+(?:light|sun))?|afternoon\s+light|evening\s+light|"
        r"warm\s+\w+\s+(?:light|glow)|soft\s+\w+\s+(?:light|glow))",
        re.I,
    ),
    re.compile(r"\s+at\s+(?:blue|golden)\s+hour\b", re.I),
    re.compile(r"\s+at\s+(?:sunset|sunrise|dawn|dusk|noon|midnight)\b", re.I),
    re.compile(
        r"\s+with\s+(?:warm|soft|cool|bright|amber|golden|cinematic)\s+"
        r"(?:ambient|directional|natural|window|tungsten|halogen|neon|"
        r"sunset|sunrise|sun|key|fill|rim|spot|track|backlight|side|"
        r"top|amber|golden|moon)?\s*(?:light|lighting|glow|tones?)\b",
        re.I,
    ),
)

# A fragment that, after stripping inline lighting, is *only* lighting
# (e.g. "morning golden light", "warm amber city lights",
# "indirect lighting"). We delete the whole fragment in that case.
# Backed by ``classify_lighting_entry`` which says "lighting" when
# LIGHTING_KW dominates and LOCATION_KW is absent.

# Extra time-of-day phrases that ``classify_lighting_entry`` may miss
# because LIGHTING_KW does not include the bare nouns. Strip these
# when they appear as a standalone fragment.
_TIME_ONLY_FRAGMENTS = re.compile(
    r"^\s*(?:morning|afternoon|evening|night|midnight|noon|dawn|dusk|"
    r"twilight|blue\s+hour|golden\s+hour)\s*$",
    re.I,
)

# Time-of-day vocab we surface into ``ambient.time_of_day`` when the
# author's lighting pool mentions it. Order matters — earlier hits win
# (so "blue hour" beats the bare "hour" in LIGHTING_KW).
_TIME_OF_DAY_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bblue\s+hour\b", re.I), "blue hour"),
    (re.compile(r"\bgolden\s+hour\b", re.I), "golden hour"),
    (re.compile(r"\b(?:sunrise|dawn)\b", re.I), "sunrise"),
    (re.compile(r"\b(?:sunset|dusk)\b", re.I), "sunset"),
    (re.compile(r"\bmidday\b|\bnoon\b", re.I), "midday"),
    (re.compile(r"\bmorning\b", re.I), "morning"),
    (re.compile(r"\bafternoon\b", re.I), "afternoon"),
    (re.compile(r"\bevening\b", re.I), "evening"),
    (re.compile(r"\bnight\b", re.I), "night"),
)


def _strip_inline_lighting(fragment: str) -> str:
    """Remove inline lighting modifiers from ``fragment``.

    Iteratively applies :data:`_INLINE_LIGHTING_PATTERNS` until the
    fragment is stable, then trims whitespace and dangling
    punctuation.
    """
    out = fragment
    while True:
        prev = out
        for rx in _INLINE_LIGHTING_PATTERNS:
            out = rx.sub("", out)
        if out == prev:
            break
    return out.strip(" \t,.;:")


def _is_pure_lighting_fragment(fragment: str) -> bool:
    """Return True when *fragment* is a standalone lighting clause.

    Uses the audit's classifier (``"lighting"`` verdict) and the
    bare-time-of-day catch-all so we also drop fragments like
    ``"morning"`` or ``"blue hour"`` that LIGHTING_KW does not match
    by themselves.
    """
    cleaned = fragment.strip(" \t,.;:")
    if not cleaned:
        return True
    if _TIME_ONLY_FRAGMENTS.match(cleaned):
        return True
    return classify_lighting_entry(cleaned) == "lighting"


def derive_scene_anchor(base_scene: str) -> str:
    """Return *base_scene* with lighting / time-of-day fragments removed.

    Splits on commas (the v2 catalog convention) so we can reason
    fragment-by-fragment, then strips inline lighting modifiers from
    fragments that survive the per-fragment lighting filter.

    Examples
    --------
    >>> derive_scene_anchor(
    ...     "Parisian boulevard with Eiffel Tower landmark visible in "
    ...     "sharp detail, morning golden light, cafe table with croissant "
    ...     "and coffee visible"
    ... )
    'Parisian boulevard with Eiffel Tower landmark visible in sharp detail, cafe table with croissant and coffee visible'
    """
    src = (base_scene or "").strip()
    if not src:
        return ""

    fragments = [f.strip() for f in src.split(",")]
    kept: list[str] = []
    for fragment in fragments:
        cleaned = _strip_inline_lighting(fragment)
        if not cleaned:
            continue
        if _is_pure_lighting_fragment(cleaned):
            continue
        kept.append(cleaned)

    return ", ".join(kept).strip()


def derive_lighting_pool(context_slots: dict[str, Any]) -> list[str]:
    """Pure-lighting strings from ``context_slots.lighting``."""
    raw_lights = context_slots.get("lighting") or []
    out: list[str] = []
    seen: set[str] = set()
    for value in raw_lights:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        if classify_lighting_entry(cleaned) != "lighting":
            continue
        out.append(cleaned)
        seen.add(cleaned)
    return out


def derive_time_of_day_pool(lighting_pool: list[str]) -> list[str]:
    """Heuristically extract time-of-day labels from a lighting pool.

    Returns labels in pool order (first occurrence wins), with
    duplicates removed. Empty when the lighting pool contains nothing
    time-coded.
    """
    out: list[str] = []
    seen: set[str] = set()
    for entry in lighting_pool:
        for rx, label in _TIME_OF_DAY_HINTS:
            if rx.search(entry) and label not in seen:
                out.append(label)
                seen.add(label)
    return out


# --- Curated overrides ----------------------------------------------------


def _load_curated() -> dict[str, dict[str, Any]]:
    """Read ``curated.json`` next to this script. Missing file → empty."""
    if not CURATED_PATH.is_file():
        return {}
    raw = json.loads(CURATED_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, dict) and not k.startswith("_")}


# --- Per-style migration --------------------------------------------------


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str) and v.strip()]
    return []


def _ambient_block(
    *,
    auto_lighting: list[str],
    auto_weather: list[str],
    auto_time_of_day: list[str],
    auto_season: list[str],
    curated_ambient: dict[str, Any] | None,
) -> dict[str, list[str]]:
    """Compose the v3 ``ambient`` block from auto + curated values."""
    curated = curated_ambient or {}

    def _pick(channel: str, auto: list[str]) -> list[str]:
        c = curated.get(channel)
        if isinstance(c, list):
            return _coerce_str_list(c)
        return auto

    return {
        "lighting": _pick("lighting", auto_lighting),
        "weather": _pick("weather", auto_weather),
        "time_of_day": _pick("time_of_day", auto_time_of_day),
        "season": _pick("season", auto_season),
    }


def migrate_style(
    entry: dict[str, Any],
    curated: dict[str, Any] | None,
) -> dict[str, Any]:
    """Migrate one style row in place, returning a per-row diff record.

    Returns a dict with ``id``, ``status`` (``"migrated"``,
    ``"already"``, ``"skipped"``), ``reasons`` (list of strings),
    ``trigger_pool_size``, ``ambient_size`` for the run summary.
    """
    sid = entry.get("id", "<unknown>")
    curated = curated or {}
    reasons: list[str] = []

    base_scene = (entry.get("base_scene") or "").strip()
    if not base_scene:
        bg = entry.get("background") or {}
        base_scene = (bg.get("base") or "").strip()

    auto_scene_anchor = derive_scene_anchor(base_scene)
    scene_anchor = (
        str(curated.get("scene_anchor") or "").strip() or auto_scene_anchor
    )
    if not scene_anchor:
        return {
            "id": sid,
            "status": "skipped",
            "reasons": ["empty scene_anchor after stripping"],
            "trigger_pool_size": 0,
            "ambient_size": {},
        }

    curated_pool = _coerce_str_list(curated.get("trigger_pool"))
    if curated_pool:
        trigger_pool = curated_pool
    else:
        # Fallback: scene_anchor itself carries the headline motif (the
        # landmark / interior). Wrapping it in a single-element pool
        # guarantees the slot sampler always materialises the motif
        # into the prompt.
        trigger_pool = [scene_anchor]
        reasons.append("trigger_pool defaulted to [scene_anchor]")

    if not trigger_pool:
        return {
            "id": sid,
            "status": "skipped",
            "reasons": ["empty trigger_pool"],
            "trigger_pool_size": 0,
            "ambient_size": {},
        }

    bg = entry.get("background") or {}
    auto_overrides = _coerce_str_list(bg.get("overrides_allowed"))
    curated_overrides = _coerce_str_list(curated.get("scene_overrides"))
    scene_overrides = curated_overrides or auto_overrides

    auto_lighting = derive_lighting_pool(entry.get("context_slots") or {})
    weather_block = entry.get("weather") or {}
    auto_weather = (
        _coerce_str_list(weather_block.get("allowed"))
        if weather_block.get("enabled")
        else []
    )
    auto_time_of_day = derive_time_of_day_pool(auto_lighting)
    auto_season: list[str] = []

    ambient = _ambient_block(
        auto_lighting=auto_lighting,
        auto_weather=auto_weather,
        auto_time_of_day=auto_time_of_day,
        auto_season=auto_season,
        curated_ambient=curated.get("ambient") if isinstance(curated.get("ambient"), dict) else None,
    )

    background_lock = (
        str(curated.get("background_lock") or "").strip()
        or str(bg.get("lock") or "semi").strip()
    )

    was_v3 = int(entry.get("schema_version") or 0) == 3

    entry["schema_version"] = 3
    entry["trigger_pool"] = list(trigger_pool)
    entry["scene_anchor"] = scene_anchor
    entry["scene_overrides"] = list(scene_overrides)
    entry["background_lock"] = background_lock
    entry["ambient"] = {k: list(v) for k, v in ambient.items()}

    return {
        "id": sid,
        "status": "already" if was_v3 else "migrated",
        "reasons": reasons,
        "trigger_pool_size": len(trigger_pool),
        "ambient_size": {k: len(v) for k, v in ambient.items()},
        "scene_anchor": scene_anchor,
    }


# --- IO helpers -----------------------------------------------------------


def _atomic_write(path: Path, payload: str) -> None:
    """Write *payload* to *path* via a temp file + ``os.replace``."""
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=tmp_dir, text=False)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the summary without writing data/styles.json.",
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        default=None,
        help="Only migrate the specified style ids (others are left untouched).",
    )
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    curated_map = _load_curated()
    targets = set(args.keys) if args.keys else None

    summaries: list[dict[str, Any]] = []
    for entry in styles:
        sid = entry.get("id", "<unknown>")
        if targets is not None and sid not in targets:
            summaries.append(
                {
                    "id": sid,
                    "status": "untouched",
                    "reasons": [],
                    "trigger_pool_size": 0,
                    "ambient_size": {},
                }
            )
            continue
        record = migrate_style(entry, curated_map.get(sid))
        summaries.append(record)

    migrated = [r for r in summaries if r["status"] == "migrated"]
    already = [r for r in summaries if r["status"] == "already"]
    skipped = [r for r in summaries if r["status"] == "skipped"]
    untouched = [r for r in summaries if r["status"] == "untouched"]

    curated_styles = sum(1 for r in summaries if r["id"] in curated_map)

    print(f"Total styles:      {len(summaries)}")
    print(f"  migrated:        {len(migrated)}")
    print(f"  already v3:      {len(already)}")
    print(f"  skipped:         {len(skipped)}")
    if untouched:
        print(f"  untouched:       {len(untouched)} (filtered out via --keys)")
    print(f"  curated entries: {curated_styles}")

    if skipped:
        print()
        print("Skipped (manual review needed):")
        for r in skipped:
            print(f"  - {r['id']:32s}  reasons: {r['reasons']}")

    if migrated or already:
        sample_size = min(10, len(migrated) + len(already))
        all_done = sorted(
            (r for r in summaries if r["status"] in {"migrated", "already"}),
            key=lambda x: -(x["trigger_pool_size"]),
        )
        print()
        print(f"Top {sample_size} by trigger_pool size:")
        for r in all_done[:sample_size]:
            sizes = r["ambient_size"]
            print(
                f"  {r['id']:32s}  trigger={r['trigger_pool_size']:>2d}  "
                f"light={sizes.get('lighting',0):>2d} "
                f"weather={sizes.get('weather',0):>2d} "
                f"tod={sizes.get('time_of_day',0):>2d} "
                f"season={sizes.get('season',0):>2d}"
            )

    if args.dry_run:
        print()
        print("Dry-run: data/styles.json NOT written.")
        return 0

    payload = json.dumps(styles, indent=2, ensure_ascii=False) + "\n"
    _atomic_write(STYLES_PATH, payload)
    print()
    print(f"Wrote {STYLES_PATH.relative_to(REPO_ROOT)} ({len(payload):,} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
