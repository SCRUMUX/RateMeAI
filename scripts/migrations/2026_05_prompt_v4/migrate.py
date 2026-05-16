"""Stage 4+5 migration for the prompt-pipeline-v4 overhaul (May 2026).

Two passes over ``data/styles.json``:

Pass 1 — zero out the legacy quality/identity tail
==================================================

Every v2/v3 entry currently carries a ``quality_identity.per_model_tail``
map (one full ~1100-char copy per model: ``gpt_image_2``, ``nano_banana_2``,
``flux_kontext``) plus an optional ``quality_identity.base``. Through
v1.32 those strings were a literal copy of the legacy
``PRESERVE_PHOTO_FACE_ONLY + QUALITY_PHOTO + LIGHT_INTEGRATION_PHOTO +
SCENE_BLEND_PHOTO + CAMERA_PHOTO + ANATOMY_PHOTO`` stack.

In v4 (Stage 1) the runtime defaults moved to a much shorter
``PHOTOREAL_BLOCK + PASTED_ON_GUARD`` pair, but
``model_wrappers._resolve_tail`` honours the per-style override above
the runtime default. Without zeroing the override every style would
keep emitting the v1.32 long tail forever — so this script blanks
``per_model_tail`` to ``{}`` and ``base`` to ``""`` across the catalog.
After this pass each style's wrapped prompt picks up the v4 short tail
automatically.

The script is idempotent — running it twice leaves the file unchanged
on the second pass.

Pass 2 — expand slot pools for diversity
========================================

For every outdoor / location-aware style we top up the ambient pools
(``ambient.lighting``, ``ambient.weather``, ``ambient.time_of_day``,
``ambient.season``) and the v2 ``context_slots.lighting`` so the slot
sampler has 5–8 values per channel to randomise across instead of the
3–4 we shipped in March. The change is additive — existing pool
entries are preserved verbatim and only the missing slots are filled
with sensible defaults. ``weather.enabled`` flips on for outdoor
styles, ``weather.allowed`` is topped up to ~5 entries.

Indoor / studio / document styles are left alone (no scene weather to
randomise; lighting variation is intentionally narrow for those).

Cost is unchanged: pool expansion only changes which value the sampler
picks per generation — the number of FAL calls and per-call quality
tier stay the same.

Usage::

    python scripts/migrations/2026_05_prompt_v4/migrate.py
    python scripts/migrations/2026_05_prompt_v4/migrate.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = ROOT / "data" / "styles.json"

# ---------------------------------------------------------------------------
# Default ambient pools.
#
# Two sets — outdoor and indoor — picked so the resulting prompts read
# as "real photo" cues and stay loosely consistent across pool members
# (no "neon midnight" lighting paired with "spring morning" time-of-day,
# which would force the model to invent contradictory frames). The
# style migration then merges these defaults into the existing pool
# without dropping any curated entries.
# ---------------------------------------------------------------------------

OUTDOOR_LIGHTING_DEFAULTS: tuple[str, ...] = (
    "soft golden hour",
    "warm afternoon sunlight",
    "blue hour cinematic",
    "diffused overcast daylight",
    "harsh midday sun, deep shadows",
    "neon evening, mixed practical lights",
    "after-rain reflections, cool tones",
    "dawn, soft pastel sky",
)

OUTDOOR_WEATHER_DEFAULTS: tuple[str, ...] = (
    "clear",
    "partly cloudy",
    "light overcast",
    "light drizzle",
    "after rain, glistening surfaces",
)

OUTDOOR_TIME_OF_DAY_DEFAULTS: tuple[str, ...] = (
    "early morning",
    "late morning",
    "midday",
    "late afternoon",
    "golden hour",
    "blue hour",
    "dusk",
)

OUTDOOR_SEASON_DEFAULTS: tuple[str, ...] = (
    "spring",
    "summer",
    "autumn",
    "winter",
)

INDOOR_LIGHTING_DEFAULTS: tuple[str, ...] = (
    "soft window light from the side",
    "warm interior key light, ambient practicals",
    "cool studio strobe, gentle fill",
    "diffused overhead daylight",
    "moody low-key with a single key light",
    "even softbox lighting, no harsh shadows",
)

INDOOR_TIME_OF_DAY_DEFAULTS: tuple[str, ...] = (
    "morning",
    "afternoon",
    "evening",
)

# Subset of ``location_type`` values treated as outdoor for the
# purposes of ambient.weather / ambient.time_of_day expansion. Anything
# else (``indoor`` / ``studio`` / ``document``) gets the indoor pool.
OUTDOOR_LOCATION_TYPES: frozenset[str] = frozenset(
    {"outdoor", "urban", "nature", "landmark", "rooftop", "beach"}
)


# Hand-curated trigger-pool extensions for the most-played landmark
# styles. The migration only touches a style if its current
# ``trigger_pool`` is shorter than 6 entries — manually-curated longer
# pools are preserved verbatim. Keys must match the style ``id``.
TRIGGER_POOL_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "paris_eiffel": (
        "Eiffel Tower in the background",
        "Eiffel Tower visible in sharp detail behind",
        "Parisian frame with the Eiffel Tower silhouette",
        "Eiffel Tower landmark anchoring the composition",
        "Eiffel Tower seen through tree branches",
        "Eiffel Tower mirrored on a Seine puddle",
        "Eiffel Tower glimpsed at the end of a Haussmann boulevard",
        "Eiffel Tower softly out of focus over the shoulder",
    ),
    "barcelona_sagrada": (
        "Sagrada Familia spires towering in the background",
        "Sagrada Familia facade in sharp detail behind",
        "Sagrada Familia framed through Gothic Quarter alleyway",
        "Sagrada Familia rising over Mediterranean rooftops",
        "Sagrada Familia silhouette at golden hour",
        "Sagrada Familia stained-glass light spilling onto the street",
        "Sagrada Familia seen across Plaça de Gaudí",
        "Sagrada Familia framed by palm trees",
    ),
    "rome_colosseum": (
        "Roman Colosseum looming in the background",
        "Colosseum arches in sharp detail behind",
        "Colosseum framed through Italian cypress trees",
        "Colosseum at sunset with golden warm tones",
        "Colosseum mirrored in cobblestone after rain",
        "Colosseum visible through a Roman colonnade",
        "Colosseum half-shadowed at dusk",
        "Colosseum framed beyond a Vespa-lined cobblestone street",
    ),
    "london_big_ben": (
        "Big Ben clock tower in the background",
        "Big Ben framed by Westminster bridge",
        "Big Ben rising above the Thames",
        "Big Ben silhouette at blue hour",
        "Big Ben seen through London plane trees",
        "Big Ben glowing warm at dusk",
        "Big Ben across the river with red double-decker passing",
        "Big Ben mirrored in a wet South Bank pavement",
    ),
    "nyc_times_square": (
        "Times Square neon billboards in the background",
        "Times Square crowd and lights behind",
        "Times Square reflected on wet pavement",
        "Times Square panoramic neon glow",
        "Times Square viewed from a yellow-cab window",
        "Times Square skyline backdrop with steam vents",
        "Times Square seen down 7th Avenue",
        "Times Square framed under scaffolding lights",
    ),
    "dubai_burj_khalifa": (
        "Burj Khalifa towering in the background",
        "Burj Khalifa illuminated at dusk",
        "Burj Khalifa visible above palm trees",
        "Burj Khalifa mirrored in the Dubai Fountain",
        "Burj Khalifa silhouetted against the desert sky",
        "Burj Khalifa framed by modern skyscrapers",
        "Burj Khalifa rising over Downtown Dubai",
        "Burj Khalifa framed at the end of a Boulevard avenue",
    ),
    "tokyo_shibuya": (
        "Shibuya scramble crossing in the background",
        "Shibuya neon signage glowing behind",
        "Shibuya wet pavement reflecting neon",
        "Shibuya crowd blurred in motion",
        "Shibuya alleyway lanterns in the back",
        "Shibuya skyline at blue hour",
    ),
    "venice_san_marco": (
        "Piazza San Marco architecture in the background",
        "Venetian Piazza San Marco backdrop",
        "St Mark's Campanile rising behind",
        "Venice palace arcades framing the composition",
        "St Mark's Basilica mosaic facade behind",
        "Venice gondola gliding past in the back",
        "Venice canal opening onto Piazza San Marco",
        "Pigeons taking flight over Piazza San Marco",
    ),
    "santorini_blue": (
        "Santorini white-and-blue domes in the background",
        "Santorini caldera view behind",
        "Santorini whitewashed steps cascading down",
        "Santorini sunset over the Aegean",
        "Santorini blue dome framing the composition",
        "Santorini tavern bougainvillea in the foreground",
    ),
    "nyc_brooklyn_bridge": (
        "Brooklyn Bridge cables towering above",
        "Brooklyn Bridge stone arches behind",
        "Brooklyn Bridge framed by the Manhattan skyline",
        "Brooklyn Bridge mirrored on the East River",
        "Brooklyn Bridge at golden hour with warm tones",
        "Brooklyn Bridge silhouette at blue hour",
        "Brooklyn Bridge walkway with cables fanning out",
        "Brooklyn Bridge framed by Dumbo cobblestones",
    ),
    "sf_golden_gate": (
        "Golden Gate Bridge cables in the background",
        "Golden Gate Bridge towers in fog",
        "Golden Gate Bridge framed by Marin headlands",
        "Golden Gate Bridge at sunset with warm tones",
        "Golden Gate Bridge mirrored in a Pacific tide pool",
        "Golden Gate Bridge silhouette at blue hour",
        "Golden Gate Bridge seen from Crissy Field",
        "Golden Gate Bridge half-veiled by rolling fog",
    ),
    "sydney_opera": (
        "Sydney Opera House sails in the background",
        "Sydney Opera House framed by harbour bridge",
        "Sydney Opera House mirrored on the harbour",
        "Sydney Opera House silhouette at golden hour",
        "Sydney Opera House at blue hour with warm interior lights",
        "Sydney Opera House framed by ferries gliding past",
        "Sydney Opera House seen from Mrs Macquarie's Point",
        "Sydney Opera House lit up at dusk",
    ),
}


# Gender-neutral wardrobe pool used to top up ``clothing.allowed`` on
# styles where the curated pool is empty. Kept generic so it reads
# plausibly on dating / social outdoor scenes regardless of gender.
NEUTRAL_OUTDOOR_WARDROBE: tuple[str, ...] = (
    "fitted neutral knit and dark jeans, clean white sneakers",
    "smart casual: tailored chinos, fitted shirt, leather loafers",
    "elevated streetwear: minimal hoodie, tailored trousers, clean trainers",
    "linen shirt over a crisp tee, beige chinos, espadrilles",
    "soft cardigan over a tee, dark jeans, simple boots",
    "lightweight blazer over a basic tee, slim trousers, white sneakers",
)


def _merge_pool(existing: Iterable[str], defaults: Iterable[str], target_size: int) -> list[str]:
    """Top up ``existing`` with ``defaults`` until ``target_size``.

    Preserves the order of existing entries, then appends defaults in
    declaration order skipping any duplicates (case-insensitive).
    Returns a list with at most ``target_size`` entries.
    """
    out: list[str] = []
    seen: set[str] = set()
    for value in list(existing) + list(defaults):
        if not isinstance(value, str):
            continue
        v = value.strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
        if len(out) >= target_size:
            break
    return out


# ---------------------------------------------------------------------------
# Pass 1 — zero out per_model_tail / quality_identity.base.
# ---------------------------------------------------------------------------


def _zero_quality_identity(style: dict, *, stats: dict[str, int]) -> bool:
    """Blank out ``quality_identity.per_model_tail`` and ``.base``.

    Returns True if the style was modified.
    """
    qi = style.get("quality_identity")
    if not isinstance(qi, dict):
        return False
    changed = False
    if qi.get("per_model_tail"):
        qi["per_model_tail"] = {}
        changed = True
        stats["per_model_tail_zeroed"] = stats.get("per_model_tail_zeroed", 0) + 1
    if qi.get("base"):
        qi["base"] = ""
        changed = True
        stats["base_zeroed"] = stats.get("base_zeroed", 0) + 1
    return changed


# ---------------------------------------------------------------------------
# Pass 2 — expand slot pools.
# ---------------------------------------------------------------------------


def _is_outdoor(style: dict) -> bool:
    loc = str(style.get("location_type") or "").strip().lower()
    if loc:
        return loc in OUTDOOR_LOCATION_TYPES
    # Fallback heuristic for legacy entries without ``location_type``:
    # treat anything except documents/studio as outdoor for pool
    # expansion purposes — the resulting weather/time-of-day options
    # are always applicable when the style mentions a location.
    style_type = str(style.get("type") or "").strip().lower()
    if style_type in {"document", "studio", "indoor"}:
        return False
    base = str(style.get("base_scene") or "").lower()
    indoor_tokens = ("studio", "office", "indoor", "interior", "passport", "id ")
    if any(tok in base for tok in indoor_tokens):
        return False
    return True


def _expand_ambient(style: dict, *, stats: dict[str, int]) -> bool:
    ambient = style.get("ambient")
    if not isinstance(ambient, dict):
        ambient = {}
        style["ambient"] = ambient

    outdoor = _is_outdoor(style)

    lighting_defaults = (
        OUTDOOR_LIGHTING_DEFAULTS if outdoor else INDOOR_LIGHTING_DEFAULTS
    )
    tod_defaults = (
        OUTDOOR_TIME_OF_DAY_DEFAULTS if outdoor else INDOOR_TIME_OF_DAY_DEFAULTS
    )

    changed = False

    # Lighting — top up to 8 entries (outdoor) / 6 (indoor).
    target_lighting = 8 if outdoor else 6
    cur_lighting = ambient.get("lighting") or []
    new_lighting = _merge_pool(cur_lighting, lighting_defaults, target_lighting)
    if new_lighting != list(cur_lighting):
        ambient["lighting"] = new_lighting
        changed = True
        stats["ambient_lighting_expanded"] = stats.get("ambient_lighting_expanded", 0) + 1

    # Weather — outdoor styles get up to 5 entries; indoor stays empty.
    if outdoor:
        cur_weather = ambient.get("weather") or []
        new_weather = _merge_pool(cur_weather, OUTDOOR_WEATHER_DEFAULTS, 5)
        if new_weather != list(cur_weather):
            ambient["weather"] = new_weather
            changed = True
            stats["ambient_weather_expanded"] = stats.get("ambient_weather_expanded", 0) + 1

    # Time of day — outdoor 5+, indoor 3.
    target_tod = 5 if outdoor else 3
    cur_tod = ambient.get("time_of_day") or []
    new_tod = _merge_pool(cur_tod, tod_defaults, target_tod)
    if new_tod != list(cur_tod):
        ambient["time_of_day"] = new_tod
        changed = True
        stats["ambient_time_of_day_expanded"] = stats.get("ambient_time_of_day_expanded", 0) + 1

    # Season — outdoor 4 (full year), indoor untouched.
    if outdoor:
        cur_season = ambient.get("season") or []
        new_season = _merge_pool(cur_season, OUTDOOR_SEASON_DEFAULTS, 4)
        if new_season != list(cur_season):
            ambient["season"] = new_season
            changed = True
            stats["ambient_season_expanded"] = stats.get("ambient_season_expanded", 0) + 1

    return changed


def _expand_v2_lighting(style: dict, *, stats: dict[str, int]) -> bool:
    """Mirror ambient.lighting into ``context_slots.lighting`` for the v2 path.

    ``unified_prompt_v2_enabled`` is on in production but
    ``style_schema_v3_enabled`` is opt-in — so the live path picks
    ``context_slots.lighting`` from the v2 reader. Keeping both pools
    in sync means the diversity buff lands on every deployment regardless
    of v3 status.
    """
    ambient_lighting = style.get("ambient", {}).get("lighting") or []
    if not ambient_lighting:
        return False
    ctx = style.get("context_slots")
    if not isinstance(ctx, dict):
        ctx = {}
        style["context_slots"] = ctx
    cur = ctx.get("lighting") or []
    new = _merge_pool(cur, ambient_lighting, max(8, len(ambient_lighting)))
    if new != list(cur):
        ctx["lighting"] = new
        stats["context_slots_lighting_expanded"] = (
            stats.get("context_slots_lighting_expanded", 0) + 1
        )
        return True
    return False


def _expand_weather_block(style: dict, *, stats: dict[str, int]) -> bool:
    """Mirror ambient.weather into the v2 ``weather`` block for outdoor styles."""
    if not _is_outdoor(style):
        return False
    ambient_weather = style.get("ambient", {}).get("weather") or []
    if not ambient_weather:
        return False
    block = style.get("weather")
    if not isinstance(block, dict):
        block = {"enabled": False, "allowed": [], "default_na": True}
        style["weather"] = block
    changed = False
    if not block.get("enabled"):
        block["enabled"] = True
        block["default_na"] = False
        changed = True
        stats["weather_enabled_flipped"] = stats.get("weather_enabled_flipped", 0) + 1
    cur_allowed = block.get("allowed") or []
    new_allowed = _merge_pool(cur_allowed, ambient_weather, 5)
    if new_allowed != list(cur_allowed):
        block["allowed"] = new_allowed
        changed = True
        stats["weather_allowed_expanded"] = stats.get("weather_allowed_expanded", 0) + 1
    return changed


def _expand_trigger_pool(style: dict, *, stats: dict[str, int]) -> bool:
    style_id = str(style.get("id") or "")
    extensions = TRIGGER_POOL_EXTENSIONS.get(style_id)
    if not extensions:
        return False
    pool = style.get("trigger_pool") or []
    if len(pool) >= 6:
        return False
    new_pool = _merge_pool(pool, extensions, 8)
    if new_pool != list(pool):
        style["trigger_pool"] = new_pool
        stats["trigger_pool_expanded"] = stats.get("trigger_pool_expanded", 0) + 1
        return True
    return False


def _expand_clothing_allowed(style: dict, *, stats: dict[str, int]) -> bool:
    """Top up ``clothing.allowed`` for outdoor styles with no curated wardrobe.

    Skips styles that already curated 3+ entries OR that have a
    gender-specific default (heuristic: ``clothing.gender_neutral=False``)
    to avoid breaking gendered curation. The fallback wardrobe is
    intentionally minimal — six gender-neutral options that look
    plausible on most dating/social outdoor scenes.
    """
    if not _is_outdoor(style):
        return False
    clothing = style.get("clothing")
    if not isinstance(clothing, dict):
        return False
    allowed = clothing.get("allowed") or []
    if len(allowed) >= 3:
        return False
    if clothing.get("gender_neutral") is False:
        return False
    new_allowed = _merge_pool(allowed, NEUTRAL_OUTDOOR_WARDROBE, 6)
    if new_allowed != list(allowed):
        clothing["allowed"] = new_allowed
        stats["clothing_allowed_expanded"] = (
            stats.get("clothing_allowed_expanded", 0) + 1
        )
        return True
    return False


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--keys",
        nargs="*",
        default=None,
        help="Limit the migration to specific style ids.",
    )
    args = parser.parse_args()

    raw = STYLES_PATH.read_text(encoding="utf-8")
    styles = json.loads(raw)
    if not isinstance(styles, list):
        print(f"unexpected styles.json shape: {type(styles).__name__}", file=sys.stderr)
        return 1

    keys_filter = set(args.keys or []) or None
    stats: dict[str, int] = {}
    modified = 0

    for style in styles:
        if not isinstance(style, dict):
            continue
        if keys_filter and str(style.get("id") or "") not in keys_filter:
            continue
        changed = False
        # Pass 1.
        if _zero_quality_identity(style, stats=stats):
            changed = True
        # Pass 2.
        if _expand_ambient(style, stats=stats):
            changed = True
        if _expand_v2_lighting(style, stats=stats):
            changed = True
        if _expand_weather_block(style, stats=stats):
            changed = True
        if _expand_trigger_pool(style, stats=stats):
            changed = True
        if _expand_clothing_allowed(style, stats=stats):
            changed = True
        if changed:
            modified += 1

    print(f"Styles processed: {len(styles)}")
    print(f"Styles modified:  {modified}")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    if args.dry_run:
        print("(dry run — no file written)")
        return 0

    STYLES_PATH.write_text(
        json.dumps(styles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {STYLES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
