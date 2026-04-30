"""Style loader v3 — registers ``schema_version: 3`` JSON entries.

Stage 1 of the prompt-pipeline-overhaul (2026-04). Strictly additive
on top of :mod:`src.services.style_loader_v2`: the v1 / v2 loaders
keep handling every entry that does NOT carry ``"schema_version": 3``,
and this loader picks out the v3-tagged entries and registers them
into :data:`src.prompts.image_gen.STYLE_REGISTRY` via the v3-specific
``register_v3`` method.

Gated by :data:`src.config.settings.style_schema_v3_enabled`. When
the flag is off (the default until Stage 2 ships data), this function
short-circuits and registers nothing — making it safe to wire into
worker startup ahead of the data migration.

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
    SCHEMA_VERSION_V3,
    StyleSpecV3,
)


logger = logging.getLogger(__name__)


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

    from src.prompts.style_spec import _DOCUMENT_STYLE_KEYS, detect_needs_full_body

    is_doc = key in _DOCUMENT_STYLE_KEYS
    aspect = "square_hd" if is_doc else "portrait_4_3"
    gen_mode = "scene_preserve" if is_doc else "identity_scene"

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
            output_aspect=aspect,  # type: ignore[arg-type]
            generation_mode=gen_mode,  # type: ignore[arg-type]
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
    try:
        from src.config import settings
    except Exception:
        settings = None

    if raw_styles is None:
        from src.services.style_loader import load_styles_from_json

        raw_styles = load_styles_from_json()

    if settings is not None and not getattr(
        settings, "style_schema_v3_enabled", False
    ):
        logger.debug("style_loader_v3: flag off, skipping registration")
        return 0

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
