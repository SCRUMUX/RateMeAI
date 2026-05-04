"""Audit — find v3 styles whose ``season`` pool clashes with the
default clothing.

Usage::

    python -m scripts.migrations.2026_05_coherence.audit_seasonal_clothing

Read-only. Output goes to stdout AND to ``audit_report.json`` next
to this file. Used by ``migrate.py`` (sibling) to drive the
``coherence`` payload.

Heuristic:

* For each v3 outdoor / mixed style with non-empty ``ambient.season``
  containing at least one of {winter, summer}, scan the default
  clothing string for "summer" / "winter" tokens. If the default
  clothing is summer-coded but the season pool contains "winter"
  (or vice versa), the entry is flagged.
* Yacht / beach / pool styles are flagged additionally if "winter"
  is in the season pool — the scenario itself is summer-coded
  semantically.
* Ski / snow styles are flagged if "summer" is in the season pool.

The flag is a *suggestion* — final decisions live in ``migrate.py``
where an operator reviews the proposed coherence rules before
applying.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
REPORT_PATH = Path(__file__).parent / "audit_report.json"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Tokens in the default clothing string that signal a summer-coded
# default (light fabrics, exposed skin, beach attire). The match is
# case-insensitive substring.
SUMMER_CLOTHING_TOKENS: tuple[str, ...] = (
    "linen",
    "summer dress",
    "sundress",
    "swimsuit",
    "bikini",
    "swim trunks",
    "shorts",
    "tank top",
    "sleeveless",
    "flip flops",
    "sandals",
    "espadrilles",
    "open-toe",
    "open shoulders",
    "bare arms",
    "beachwear",
    "sun hat",
    "straw hat",
    "tropical print",
    "floral sundress",
    "white t-shirt",
    "light cotton",
)


WINTER_CLOTHING_TOKENS: tuple[str, ...] = (
    "parka",
    "winter coat",
    "down jacket",
    "puffer",
    "puffer jacket",
    "snow boots",
    "winter boots",
    "scarf",
    "fur",
    "fur-lined",
    "mittens",
    "thermal",
    "wool sweater",
    "ski jacket",
    "ski suit",
    "balaclava",
    "knit beanie",
    "thick coat",
    "trench coat",
)


# Style keys whose name semantically encodes "summer" — winter season
# in the pool is almost certainly nonsense.
SUMMER_BIASED_KEYS: tuple[str, ...] = (
    "yacht",
    "beach",
    "pool",
    "tropical",
    "surf",
    "sailing",
    "marina",
    "tropic",
    "swim",
    "miami_beach",
    "maldives",
    "santorini",
    "bali",
    "cabana",
    "resort",
)


WINTER_BIASED_KEYS: tuple[str, ...] = (
    "ski",
    "snow",
    "winter_",
    "ice_",
    "alps",
    "snowboard",
    "skate_winter",
    "frosty",
    "blizzard",
)


def _has_token(haystack: str, tokens: tuple[str, ...]) -> bool:
    needle = (haystack or "").lower()
    return any(t in needle for t in tokens)


def _key_matches(key: str, biased: tuple[str, ...]) -> bool:
    norm = (key or "").lower()
    return any(b in norm for b in biased)


def _flatten_clothing_default(spec: dict[str, Any]) -> str:
    """Concatenate per-gender clothing defaults into one string for
    token scanning. Some entries store ``default`` as a string instead
    of a dict; handle both."""
    clothing = spec.get("clothing") or {}
    default = clothing.get("default")
    if isinstance(default, str):
        return default
    if isinstance(default, dict):
        return " | ".join(str(v) for v in default.values() if v)
    legacy = spec.get("default_clothing") or ""
    return str(legacy)


def main() -> None:
    styles: list[dict[str, Any]] = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    v3 = [s for s in styles if int(s.get("schema_version") or 0) == 3]

    print(f"Total styles: {len(styles)}")
    print(f"v3 styles:    {len(v3)}")
    print()

    flagged: list[dict[str, Any]] = []
    season_buckets: dict[str, list[str]] = {
        "winter": [],
        "summer": [],
        "spring": [],
        "autumn": [],
    }

    for spec in v3:
        sid = str(spec.get("id") or "")
        ambient = spec.get("ambient") or {}
        seasons = [str(s).strip().lower() for s in (ambient.get("season") or [])]
        if not seasons:
            continue
        location = str(spec.get("location_type") or "").strip().lower()
        if location not in ("outdoor", "mixed", ""):
            # indoor / document — season makes little sense; out of
            # scope for this audit (already covered by indoor lint).
            continue

        for s in seasons:
            if s in season_buckets:
                season_buckets[s].append(sid)

        clothing_str = _flatten_clothing_default(spec)
        is_summer_clothing = _has_token(clothing_str, SUMMER_CLOTHING_TOKENS)
        is_winter_clothing = _has_token(clothing_str, WINTER_CLOTHING_TOKENS)

        flags: list[str] = []
        if "winter" in seasons and is_summer_clothing:
            flags.append("WINTER_SEASON_SUMMER_CLOTHING")
        if "summer" in seasons and is_winter_clothing:
            flags.append("SUMMER_SEASON_WINTER_CLOTHING")
        if _key_matches(sid, SUMMER_BIASED_KEYS) and "winter" in seasons:
            flags.append("SUMMER_BIASED_KEY_WITH_WINTER")
        if _key_matches(sid, WINTER_BIASED_KEYS) and "summer" in seasons:
            flags.append("WINTER_BIASED_KEY_WITH_SUMMER")

        if flags:
            flagged.append(
                {
                    "id": sid,
                    "mode": str(spec.get("mode") or ""),
                    "location_type": location or "(unset)",
                    "seasons": seasons,
                    "clothing_default": clothing_str,
                    "flags": flags,
                }
            )

    print(f"Outdoor/mixed v3 styles with season pool: {sum(len(v) for v in season_buckets.values())}")
    print(f"  winter:  {len(season_buckets['winter']):3d}")
    print(f"  summer:  {len(season_buckets['summer']):3d}")
    print(f"  spring:  {len(season_buckets['spring']):3d}")
    print(f"  autumn:  {len(season_buckets['autumn']):3d}")
    print()
    print(f"Flagged styles: {len(flagged)}")
    print()
    for entry in flagged[:40]:
        print(f"  {entry['id']:35s} {','.join(entry['flags'])}")
        print(f"    seasons={entry['seasons']}")
        print(f"    clothing={entry['clothing_default'][:100]}")
        print()

    REPORT_PATH.write_text(
        json.dumps(
            {
                "total_v3": len(v3),
                "season_buckets": season_buckets,
                "flagged": flagged,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Report written → {REPORT_PATH}")


if __name__ == "__main__":
    main()
