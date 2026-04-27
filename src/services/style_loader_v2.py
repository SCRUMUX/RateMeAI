"""Style loader v2 — registers ``schema_version: 2`` JSON entries.

PR1 of the style-schema-v2 migration. Additive: the v1 loader in
:mod:`src.services.style_loader` keeps handling every entry regardless
of schema version. This loader picks out ONLY the entries tagged
``"schema_version": 2`` and registers them into
:data:`src.prompts.style_spec.STYLE_REGISTRY` via the v2-specific
``register_v2`` method so the v1 lookup map is not contaminated.

Gated by the :data:`src.config.settings.style_schema_v2_enabled`
feature flag. With the flag off this function is still safe to call
(e.g. from the worker start-up), but it short-circuits and registers
nothing.
"""

from __future__ import annotations

import logging
from typing import Any

from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    BackgroundSlot,
    ClothingSlot,
    QualityBlock,
    SCHEMA_VERSION,
    StyleSpecV2,
    WeatherPolicy,
)


logger = logging.getLogger(__name__)


def _tuple(values: Any) -> tuple[str, ...]:
    if not values:
        return ()
    if isinstance(values, list):
        return tuple(str(v) for v in values if isinstance(v, (str, int, float)) and str(v))
    if isinstance(values, tuple):
        return tuple(str(v) for v in values if isinstance(v, (str, int, float)) and str(v))
    return ()


def _clothing_default_dict(raw: Any, *, legacy_str: Any = None) -> dict[str, str]:
    """Normalise ``clothing.default`` to ``{male, female, neutral}``.

    Accepts:

    * a dict with any subset of ``{"male", "female", "neutral"}`` —
      missing keys are filled from ``neutral`` (or any non-empty value)
      so the runtime never has to second-guess fallbacks;
    * a plain string (legacy v2 entries pre-1.27.3) — copied into all
      three keys so behaviour is identical to before;
    * ``None`` / empty — falls back to ``legacy_str`` (the v1
      ``default_clothing`` field) for the same reason.

    Output keys are always exactly ``{"male", "female", "neutral"}``.
    """
    fill: str = ""
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


def _lock_level(raw: Any, legacy_type: str) -> BackgroundLockLevel:
    """Map JSON ``background.lock`` (v2) or legacy ``type`` to an enum.

    ``scene_locked`` → locked, ``semi_locked`` → semi, ``flexible`` →
    flexible. Accepts the v2 canonical strings as-is.
    """
    candidate = str(raw or legacy_type or "flexible").strip().lower()
    mapping = {
        "locked": BackgroundLockLevel.LOCKED,
        "scene_locked": BackgroundLockLevel.LOCKED,
        "semi": BackgroundLockLevel.SEMI,
        "semi_locked": BackgroundLockLevel.SEMI,
        "flexible": BackgroundLockLevel.FLEXIBLE,
    }
    return mapping.get(candidate, BackgroundLockLevel.FLEXIBLE)


def _to_v2(raw: dict[str, Any]) -> StyleSpecV2 | None:
    """Convert a single v2-tagged JSON entry to a :class:`StyleSpecV2`.

    Returns None if the entry is malformed; errors are logged and
    the loader moves on (missing a style is better than crashing the
    worker at startup).
    """
    if int(raw.get("schema_version") or 0) != SCHEMA_VERSION:
        return None

    try:
        key = str(raw["id"])
        mode = str(raw["mode"])
    except KeyError as exc:
        logger.warning("style_loader_v2: missing required field %s in %r", exc, raw)
        return None

    from src.prompts.style_spec import _DOCUMENT_STYLE_KEYS, detect_needs_full_body

    is_doc = key in _DOCUMENT_STYLE_KEYS

    bg_raw = raw.get("background") or {}
    if not isinstance(bg_raw, dict):
        bg_raw = {}
    background = BackgroundSlot(
        base=str(bg_raw.get("base") or raw.get("base_scene") or ""),
        lock=_lock_level(bg_raw.get("lock"), raw.get("type", "flexible")),
        overrides_allowed=_tuple(bg_raw.get("overrides_allowed")),
    )

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

    weather_raw = raw.get("weather") or {}
    if not isinstance(weather_raw, dict):
        weather_raw = {}
    weather = WeatherPolicy(
        enabled=bool(weather_raw.get("enabled", False)),
        allowed=_tuple(weather_raw.get("allowed")),
        default_na=bool(weather_raw.get("default_na", True)),
    )

    # context_slots stays as a plain dict (tuple per channel); absent
    # keys fall back to reasonable defaults so the UI always gets
    # something to draw when a channel is relevant.
    slots_raw = raw.get("context_slots") or {}
    if not isinstance(slots_raw, dict):
        slots_raw = {}
    context_slots = {
        k: _tuple(v) for k, v in slots_raw.items() if isinstance(v, list)
    }

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

    gen_mode = "scene_preserve" if is_doc else "identity_scene"
    aspect = "square_hd" if is_doc else "portrait_4_3"

    return StyleSpecV2(
        key=key,
        mode=mode,
        trigger=str(raw.get("trigger") or ""),
        background=background,
        clothing=clothing,
        weather=weather,
        context_slots=context_slots,
        quality_identity=quality_identity,
        expression=str(raw.get("expression") or ""),
        needs_full_body=detect_needs_full_body(key, mode),
        output_aspect=aspect,  # type: ignore[arg-type]
        generation_mode=gen_mode,  # type: ignore[arg-type]
    )


def register_v2_styles_from_json(
    raw_styles: list[dict[str, Any]] | None = None,
) -> int:
    """Register every v2-tagged entry from ``data/styles.json``.

    Returns the number of StyleSpecV2 instances registered. Safe to
    call when the feature flag is off — it still loads the file but
    registers nothing if no entries have ``schema_version==2``.

    Args:
        raw_styles: pass an already-loaded list to avoid re-reading
            the JSON file (used by tests).
    """
    try:
        from src.config import settings
    except Exception:
        settings = None

    if raw_styles is None:
        from src.services.style_loader import load_styles_from_json

        raw_styles = load_styles_from_json()

    if settings is not None and not getattr(
        settings, "style_schema_v2_enabled", False
    ):
        logger.debug("style_loader_v2: flag off, skipping registration")
        return 0

    from src.prompts.image_gen import STYLE_REGISTRY

    registered = 0
    for entry in raw_styles:
        spec = _to_v2(entry)
        if spec is None:
            continue
        STYLE_REGISTRY.register_v2(spec)
        registered += 1

    if registered:
        logger.info(
            "style_loader_v2: registered %d StyleSpecV2 entries", registered
        )
    return registered
