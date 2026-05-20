"""Style loader v3 — registers ``schema_version: 3`` JSON entries.

Stage 1 of the prompt-pipeline-overhaul (2026-04). Strictly additive
on top of :mod:`src.services.style_loader_v2`: the v1 / v2 loaders
keep handling every entry that does NOT carry ``"schema_version": 3``,
and this loader picks out the v3-tagged entries and registers them
into :data:`src.prompts.image_gen.STYLE_REGISTRY` via the v3-specific
``register_v3`` method.

Historically gated by ``settings.style_schema_v3_enabled``; as of
v1.70.x the flag is always-on in every environment because Stage 2
shipped data for every catalogue style. The branch that reads the
flag remains for emergency rollback but the loader always runs.

JSON schema accepted (v3-only fields are required; everything else
mirrors v2 so the migration script can re-emit the same file):

.. code-block:: json

    {
      "id": "burj_khalifa",
      "mode": "social",
      "schema_version": 3,
      "trigger_pool": [
        "Burj Khalifa skyline at twilight",
        "Burj Khalifa lit at night across the marina",
        "rooftop terrace with the Burj Khalifa silhouette"
      ],
      "scene_anchor": "open-air observation terrace overlooking the Dubai skyline",
      "scene_overrides": [
        "luxury rooftop bar overlooking downtown Dubai",
        "marina promenade with skyscrapers across the water"
      ],
      "background_lock": "semi",
      "ambient": {
        "lighting": ["soft golden", "blue hour", "warm cinematic"],
        "weather": ["clear", "overcast", "light haze"],
        "time_of_day": ["evening", "night", "twilight"],
        "season": ["spring", "autumn", "winter"]
      },
      "clothing": { "default": { ... }, "allowed": [...] },
      "quality_identity": { "base": "...", "per_model_tail": {...} },
      "expression": "calm confident expression"
    }

Malformed entries are logged and skipped — missing one style is far
preferable to crashing the worker at startup.
"""

from __future__ import annotations

import logging
from typing import Any

from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    ClothingSlot,
    QualityBlock,
)
from src.prompts.style_schema_v3 import (
    AmbientPools,
    CONFIGURABLE_CHANNELS,
    CoherenceRule,
    LOCATION_TYPES,
    LOCATION_TYPE_DOCUMENT,
    LOCATION_TYPE_INDOOR,
    LOCATION_TYPE_OUTDOOR,
    SCHEMA_VERSION_V3,
    StyleSpecV3,
)


logger = logging.getLogger(__name__)


_INDOOR_HINT_TOKENS: tuple[str, ...] = (
    "room", "office", "studio", "bedroom", "bathroom", "kitchen",
    "library", "indoor", "interior", "lobby", "hallway", "elevator",
    "closet", "gym interior", "gym", "indoors", "warehouse", "loft",
    "cafe", "coffee shop", "restaurant interior", "bar interior",
    "showroom", "shop", "store", "boutique", "lounge", "gallery",
    "clinic", "hospital", "stage", "venue", "podium", "armchair",
    "bookshelves", "home corner", "home desk", "minimalist setting",
    "pastel-colored wall", "minimal setting", "minimal backdrop",
    "scandinavian aesthetic", "creator setup", "creator setup",
    "ring light", "exposed brick", "marble surface", "marble floor",
)
"""Substrings that classify a scene_anchor as indoor.

Order matters only for readability. The match is a simple
case-insensitive substring scan in :func:`_infer_location_type`.

The list deliberately includes a few visually-indoor compound
phrases ("ring light", "exposed brick", "marble floor") because
several catalog entries describe a studio scene without ever
saying "studio" — they list the props instead."""


_OUTDOOR_HINT_TOKENS: tuple[str, ...] = (
    "rooftop", "terrace", "street", "park", "beach", "mountain",
    "skyline", "outdoor", "outside", "promenade", "square ", "boulevard",
    "garden", "plaza", "harbour", "harbor", "marina", "alley", "courtyard",
    "city ", "trail", "forest", "field", "desert", "lake", "river",
    "embankment", "bridge", "skyscraper", "open air", "open-air",
    "piazza", "crosswalk", "balcony", "yacht", "yacht deck", "deck",
    "bike path", "bicycle", "exterior", "meadow", "grass", "sea",
    "ocean", "tropical", "scenic", "landmark", "tropical scenery",
    "exotic location", "iconic landmark", "outdoors", "skies",
    "blue sky", "clear sky", "country road", "urban setting",
    "natural green",
)


_INDOOR_ID_HINTS: tuple[str, ...] = (
    "office", "studio", "lounge", "gallery", "shop", "store", "boutique",
    "gym", "clinic", "venue", "stage", "home", "library", "minimal",
    "pastel", "scandi", "cafe", "interior", "indoor", "lobby", "creator",
    "online_learning", "reading_", "evening_planning",
)


_OUTDOOR_ID_HINTS: tuple[str, ...] = (
    "outdoor", "beach", "park", "garden", "yacht", "marina", "skyline",
    "skyscraper", "rooftop", "balcony", "city", "street", "bridge",
    "tower", "landmark", "travel", "blogger", "exotic", "tropical",
    "mountain", "trail", "cycling", "golden_hour",
)


_AMBIGUOUS_MIXED_HINTS: tuple[str, ...] = (
    "instagram", "architecture_shadow", "decision_moment",
    "shopfront", "stage",
)
"""Style ids that the heuristic should classify as ``mixed`` rather
than leaving unclassified — visually they could go either way and
the operator can override later through the admin UI."""


_DOCUMENT_HINT_TOKENS: tuple[str, ...] = (
    "passport", "document photo", "visa photo", "id photo", "blank background",
    "white background", "neutral background",
)


def _infer_location_type(scene_anchor: str, key: str) -> str:
    """Auto-classify a style by scanning its scene anchor + id.

    Used as a fallback when the JSON entry does not declare an explicit
    ``location_type`` — keeps the lint engine useful for the long tail
    of un-curated styles.

    Lookup order (first match wins):

    1. Document tokens in scene anchor or id.
    2. Indoor / outdoor scene-anchor tokens.
    3. Indoor / outdoor id-based hints (handles styles whose anchor
       is too generic but whose id makes the intent obvious — e.g.
       ``warm_outdoor`` whose anchor is just lighting prose).
    4. Mixed fallback for known-ambiguous ids.

    Returns the empty string only when nothing matches; the lint
    engine treats that as "не классифицирован" and skips location-
    sensitive rules.
    """
    text = (scene_anchor or "").lower()
    key_lc = (key or "").lower()
    for tok in _DOCUMENT_HINT_TOKENS:
        if tok in text or tok in key_lc:
            return LOCATION_TYPE_DOCUMENT
    for tok in _INDOOR_HINT_TOKENS:
        if tok in text:
            return LOCATION_TYPE_INDOOR
    for tok in _OUTDOOR_HINT_TOKENS:
        if tok in text:
            return LOCATION_TYPE_OUTDOOR
    for tok in _OUTDOOR_ID_HINTS:
        if tok in key_lc:
            return LOCATION_TYPE_OUTDOOR
    for tok in _INDOOR_ID_HINTS:
        if tok in key_lc:
            return LOCATION_TYPE_INDOOR
    for tok in _AMBIGUOUS_MIXED_HINTS:
        if tok in key_lc:
            return "mixed"
    return ""


def _tuple(values: Any) -> tuple[str, ...]:
    if not values:
        return ()
    if isinstance(values, (list, tuple)):
        return tuple(
            str(v) for v in values if isinstance(v, (str, int, float)) and str(v).strip()
        )
    return ()


def _clothing_default_dict(raw: Any, *, legacy_str: Any = None) -> dict[str, str]:
    """Same normalisation as ``style_loader_v2._clothing_default_dict``.

    Duplicated here on purpose — the v2 loader's helper is private and
    importing it would create a vertical coupling between two loaders
    that should be free to evolve independently.
    """
    fill = ""
    bucket: dict[str, str] = {"male": "", "female": "", "neutral": ""}
    if isinstance(raw, dict):
        for k in ("male", "female", "neutral"):
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                bucket[k] = v
        fill = (
            bucket["neutral"]
            or bucket["male"]
            or bucket["female"]
            or str(legacy_str or "").strip()
        )
    elif isinstance(raw, str) and raw.strip():
        fill = raw
    else:
        fill = str(legacy_str or "").strip()

    if fill:
        for k in ("male", "female", "neutral"):
            if not bucket[k]:
                bucket[k] = fill
    return bucket


def _lock_level(raw: Any, fallback: str = "semi") -> BackgroundLockLevel:
    candidate = str(raw or fallback or "semi").strip().lower()
    mapping = {
        "locked": BackgroundLockLevel.LOCKED,
        "scene_locked": BackgroundLockLevel.LOCKED,
        "semi": BackgroundLockLevel.SEMI,
        "semi_locked": BackgroundLockLevel.SEMI,
        "flexible": BackgroundLockLevel.FLEXIBLE,
    }
    return mapping.get(candidate, BackgroundLockLevel.SEMI)


def _coherence_rules(raw: Any, *, key: str) -> tuple[CoherenceRule, ...]:
    """Parse the optional ``coherence`` array from a v3 style entry.

    Tolerant of malformed entries — bad rules are logged and dropped
    rather than crashing the loader. Duplicate seasons are caught at
    construction time by :class:`StyleSpecV3.__post_init__`; here we
    only validate per-rule shape.
    """
    if not raw:
        return ()
    if not isinstance(raw, list):
        logger.warning(
            "style_loader_v3: %s coherence must be a list, got %s — ignored",
            key,
            type(raw).__name__,
        )
        return ()
    rules: list[CoherenceRule] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            logger.warning(
                "style_loader_v3: %s coherence[%d] is not a dict — skipped",
                key,
                idx,
            )
            continue
        season = str(entry.get("season") or "").strip()
        if not season:
            logger.warning(
                "style_loader_v3: %s coherence[%d] has empty season — skipped",
                key,
                idx,
            )
            continue
        clothing_raw = entry.get("clothing_override") or {}
        if not isinstance(clothing_raw, dict):
            clothing_raw = {}
        clothing_override = {
            str(k): str(v).strip()
            for k, v in clothing_raw.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        }
        rules.append(
            CoherenceRule(
                season=season,
                clothing_override=clothing_override,
                lighting_filter=_tuple(entry.get("lighting_filter")),
                weather_filter=_tuple(entry.get("weather_filter")),
                time_of_day_filter=_tuple(entry.get("time_of_day_filter")),
            )
        )
    return tuple(rules)


def _ambient_pools(raw: Any) -> AmbientPools:
    if not isinstance(raw, dict):
        return AmbientPools()
    return AmbientPools(
        lighting=_tuple(raw.get("lighting")),
        weather=_tuple(raw.get("weather")),
        time_of_day=_tuple(raw.get("time_of_day")),
        season=_tuple(raw.get("season")),
        materials=_tuple(raw.get("materials")),
        framing_hint=_tuple(raw.get("framing_hint")),
    )


def _to_v3(raw: dict[str, Any]) -> StyleSpecV3 | None:
    if int(raw.get("schema_version") or 0) != SCHEMA_VERSION_V3:
        return None

    try:
        key = str(raw["id"])
        mode = str(raw["mode"])
    except KeyError as exc:
        logger.warning("style_loader_v3: missing required field %s in %r", exc, raw)
        return None

    trigger_pool = _tuple(raw.get("trigger_pool"))
    if not trigger_pool:
        # v3's headline guarantee: triggers are inviolable, so an entry
        # without a trigger pool is corrupt and must not silently fall
        # through to v2. We log and skip — operators see the line in
        # the worker log and can fix the data.
        legacy_trigger = str(raw.get("trigger") or "").strip()
        if legacy_trigger:
            trigger_pool = (legacy_trigger,)
        else:
            logger.error(
                "style_loader_v3: %s has empty trigger_pool — skipping. "
                "v3 styles require at least one trigger phrase.",
                key,
            )
            return None

    scene_anchor = str(raw.get("scene_anchor") or raw.get("base_scene") or "").strip()
    if not scene_anchor:
        logger.error(
            "style_loader_v3: %s has empty scene_anchor — skipping. "
            "v3 styles need a non-empty scene anchor.",
            key,
        )
        return None

    clothing_raw = raw.get("clothing") or {}
    if not isinstance(clothing_raw, dict):
        clothing_raw = {}
    clothing = ClothingSlot(
        default=_clothing_default_dict(
            clothing_raw.get("default"),
            legacy_str=raw.get("default_clothing"),
        ),
        allowed=_tuple(clothing_raw.get("allowed")),
        gender_neutral=bool(clothing_raw.get("gender_neutral", True)),
    )

    quality_raw = raw.get("quality_identity") or {}
    if not isinstance(quality_raw, dict):
        quality_raw = {}
    per_model_tail = quality_raw.get("per_model_tail") or {}
    if not isinstance(per_model_tail, dict):
        per_model_tail = {}
    quality_identity = QualityBlock(
        base=str(quality_raw.get("base") or ""),
        per_model_tail={
            str(k): str(v)
            for k, v in per_model_tail.items()
            if isinstance(k, str) and isinstance(v, str)
        },
    )

    from src.prompts.style_spec import (
        _DOCUMENT_STYLE_KEYS,
        detect_needs_full_body,
        detect_needs_torso,
    )

    is_doc = key in _DOCUMENT_STYLE_KEYS
    aspect = "square_hd" if is_doc else "portrait_4_3"

    raw_channels = raw.get("available_channels") or []
    if isinstance(raw_channels, (list, tuple)):
        available_channels: tuple[str, ...] = tuple(
            str(c) for c in raw_channels
            if isinstance(c, str) and c in CONFIGURABLE_CHANNELS
        )
    else:
        available_channels = ()

    raw_location = str(raw.get("location_type") or "").strip().lower()
    if raw_location in LOCATION_TYPES:
        location_type = raw_location
    elif is_doc:
        location_type = LOCATION_TYPE_DOCUMENT
    else:
        location_type = _infer_location_type(scene_anchor, key)

    try:
        return StyleSpecV3(
            key=key,
            mode=mode,
            trigger_pool=trigger_pool,
            scene_anchor=scene_anchor,
            scene_overrides=_tuple(raw.get("scene_overrides")),
            background_lock=_lock_level(
                raw.get("background_lock") or (raw.get("background") or {}).get("lock"),
                fallback=raw.get("type", "semi"),
            ),
            ambient=_ambient_pools(raw.get("ambient")),
            clothing=clothing,
            quality_identity=quality_identity,
            expression=str(raw.get("expression") or ""),
            needs_full_body=detect_needs_full_body(key, mode),
            needs_torso=detect_needs_torso(key, mode),
            output_aspect=aspect,  # type: ignore[arg-type]
            available_channels=available_channels,
            location_type=location_type,
            coherence=_coherence_rules(raw.get("coherence"), key=key),
        )
    except ValueError as exc:
        logger.error("style_loader_v3: rejected %s — %s", key, exc)
        return None


def register_v3_styles_from_json(
    raw_styles: list[dict[str, Any]] | None = None,
) -> int:
    """Register every v3-tagged entry from ``data/styles.json``.

    Returns the number of :class:`StyleSpecV3` instances registered.
    Safe to call when the feature flag is off — it still loads the
    file but registers nothing if no entries declare
    ``schema_version == 3``.

    Args:
        raw_styles: pre-loaded list to skip a JSON re-read (used by
            tests).
    """
    if raw_styles is None:
        from src.services.style_loader import load_styles_from_json

        raw_styles = load_styles_from_json()

    # v1.70.17: ``data/styles.json`` is 100% v3 (Phase 3.1 audit guard
    # ``test_styles_json_v3_coverage``), so the historical
    # ``_auto_promote_v2_specs`` synthesiser was retired. Every entry
    # now arrives through ``_to_v3`` directly.

    from src.prompts.image_gen import STYLE_REGISTRY

    registered = 0
    for entry in raw_styles:
        spec = _to_v3(entry)
        if spec is None:
            continue
        STYLE_REGISTRY.register_v3(spec)
        registered += 1

    if registered:
        logger.info(
            "style_loader_v3: registered %d StyleSpecV3 entries", registered
        )
    return registered
