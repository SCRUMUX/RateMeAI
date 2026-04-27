"""Composition builder for StyleSpecV2.

PR1 of the style-schema-v2 migration. Takes a v2 style spec, the mode
("dating" / "cv" / "social"), user ``input_hints``, optional ``framing``
and optional ``variant`` and produces a :class:`CompositionIR` — a
structured intermediate representation that the per-model wrappers
(:mod:`src.prompts.model_wrappers`) turn into the final string.

Why an IR and not a string?

- Lets GPT Image 2 and Nano Banana 2 wrap the same scene differently
  without duplicating the per-channel validation logic.
- Keeps per-channel whitelist checks in one place.
- Simplifies shadow-run parity tests: we can assert on the IR fields
  directly ("framing_line is expected when framing='half_body'")
  independent of the final prompt character budget.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from src.prompts.style_schema_v2 import BackgroundLockLevel, StyleSpecV2


@dataclass
class CompositionIR:
    """Structured scene description, still model-agnostic."""

    mode: str
    style_key: str
    change_instruction: str
    scene: str
    lighting: str = ""
    weather: str = ""
    clothing: str = ""
    expression: str = ""
    framing_line: str = ""
    # Quality / identity anchors collected from the style spec. The
    # model wrapper decides whether to append the common block,
    # override it with a per-model tail, or substitute the legacy
    # constants from image_gen.py for backward parity.
    quality_identity_base: str = ""
    per_model_tail_map: dict[str, str] = field(default_factory=dict)
    # For document styles the wrapper replaces the tail entirely with
    # DOC_PRESERVE / DOC_QUALITY; this flag tells it whether to.
    is_document: bool = False
    # True when the user asked for a framing override that IS in the
    # style's whitelist; surfaced in the prompt even when the user
    # doesn't touch anything else.
    framing_requested: bool = False
    # v1.27.3 — soft-substitution log. Each entry has the shape
    # ``{"channel": "lighting|scene|clothing|weather", "requested": str,
    # "applied": str}``. The executor walks this list to surface a
    # post-generation hint to the user; tests assert on it directly to
    # avoid coupling to the prompt string.
    substitutions: list[dict[str, str]] = field(default_factory=list)

    def scene_line(self) -> str:
        """Compose the single-sentence scene-and-environment description.

        Equivalent to ``VariationEngine.apply_variation`` output but
        without an embedded clothing clause (clothing is a separate
        IR field). Returns something like "Parisian boulevard, warm
        sunset lighting, clear weather.".
        """
        parts: list[str] = []
        if self.scene:
            parts.append(self.scene)
        if self.lighting:
            parts.append(f"{self.lighting} lighting")
        if self.weather:
            parts.append(f"{self.weather} weather")
        if not parts:
            return ""
        return ", ".join(p.strip() for p in parts if p and p.strip())


def _value_in_whitelist(value: str, whitelist: tuple[str, ...]) -> bool:
    return bool(value) and value in whitelist


def _soft_substitute(
    *,
    channel: str,
    requested: str,
    whitelist: tuple[str, ...],
    rng: random.Random | None,
    substitutions: list[dict[str, str]],
) -> str:
    """Pick a random whitelist value and record the substitution.

    Returns the chosen value (always non-empty when ``whitelist`` is
    non-empty). The caller is expected to have already verified that
    ``requested`` is non-empty AND not in ``whitelist``.
    """
    if not whitelist:
        # Free-text channel — passthrough is recorded in the caller.
        return requested
    chooser = rng or random
    applied = chooser.choice(whitelist)
    substitutions.append(
        {
            "channel": channel,
            "requested": requested,
            "applied": applied,
        }
    )
    return applied


def _resolve_lighting(
    spec: StyleSpecV2,
    hints: dict[str, Any],
    *,
    strict: bool,
    substitutions: list[dict[str, str]],
    rng: random.Random | None,
) -> str:
    raw = str(hints.get("lighting") or "").strip()
    if not raw:
        return ""
    allowed = spec.context_slots.get("lighting", ())
    if not strict or _value_in_whitelist(raw, allowed):
        return raw
    return _soft_substitute(
        channel="lighting",
        requested=raw,
        whitelist=allowed,
        rng=rng,
        substitutions=substitutions,
    )


def _resolve_weather(
    spec: StyleSpecV2,
    hints: dict[str, Any],
    *,
    strict: bool,
    substitutions: list[dict[str, str]],
    rng: random.Random | None,
) -> str:
    raw = str(hints.get("weather") or "").strip()
    if not raw:
        return ""
    if not spec.weather.enabled:
        return ""
    if not strict or _value_in_whitelist(raw, spec.weather.allowed):
        return raw
    return _soft_substitute(
        channel="weather",
        requested=raw,
        whitelist=spec.weather.allowed,
        rng=rng,
        substitutions=substitutions,
    )


def _resolve_scene(
    spec: StyleSpecV2,
    hints: dict[str, Any],
    *,
    strict: bool,
    substitutions: list[dict[str, str]],
    rng: random.Random | None,
) -> str:
    base = spec.background.base
    override = str(hints.get("scene_override") or "").strip()
    sub_location = str(hints.get("sub_location") or "").strip()
    background_type = str(hints.get("background_type") or "").strip()

    if spec.background.lock == BackgroundLockLevel.LOCKED:
        return base
    # The modal sends `scene_override` for both SEMI and FLEXIBLE
    # backgrounds; backend must accept either key without dropping the
    # user's choice. `background_type` is the catalog-API alias.
    user_value = sub_location or override or background_type
    if not user_value:
        return base

    allowed = spec.background.overrides_allowed
    is_known = not strict or _value_in_whitelist(user_value, allowed)
    if not is_known:
        substituted = _soft_substitute(
            channel="scene",
            requested=user_value,
            whitelist=allowed,
            rng=rng,
            substitutions=substitutions,
        )
        # If allowed is empty (free-text channel), substituted == user_value
        # and we keep the user's literal text per the "no explicit
        # validation" policy.
        user_value = substituted

    if spec.background.lock == BackgroundLockLevel.SEMI:
        return f"{user_value} in {base}" if base else user_value
    return user_value


def _resolve_clothing(
    spec: StyleSpecV2,
    hints: dict[str, Any],
    *,
    strict: bool,
    gender: str = "neutral",
    substitutions: list[dict[str, str]],
    rng: random.Random | None,
) -> str:
    override = str(hints.get("clothing_override") or "").strip()
    default = spec.clothing_for(gender)
    if not override:
        return default
    if not strict or _value_in_whitelist(override, spec.clothing.allowed):
        return override
    if not spec.clothing.allowed:
        # Free-text channel for styles without a curated wardrobe —
        # trust the user's text per the "no explicit validation" policy.
        return override
    return _soft_substitute(
        channel="clothing",
        requested=override,
        whitelist=spec.clothing.allowed,
        rng=rng,
        substitutions=substitutions,
    )


def _variation_engine_v2_enabled() -> bool:
    """Check the ``variation_engine_v2_enabled`` feature flag lazily."""
    try:
        from src.config import settings
    except Exception:
        return False
    return bool(getattr(settings, "variation_engine_v2_enabled", False))


def _resolve_framing_line(spec: StyleSpecV2, framing: str | None) -> tuple[str, bool]:
    """Return (prompt_line, was_requested) for the framing directive.

    ``was_requested`` is True when the caller passed a recognisable
    framing value (even if the style's whitelist doesn't include it —
    in that case the prompt line is empty but the IR knows the user
    asked for something).
    """
    from src.prompts.image_gen import _framing_directive

    if not framing:
        return "", False
    # Keep the exact phrasing used by v1 so golden tests can compare.
    line = _framing_directive(framing)
    return line, bool(framing)


def build_composition(
    spec: StyleSpecV2,
    *,
    mode: str,
    change_instruction: str,
    input_hints: dict[str, Any] | None = None,
    framing: str | None = None,
    gender: str = "male",
    strict: bool = True,
    is_document: bool = False,
    rng: random.Random | None = None,
) -> CompositionIR:
    """Produce a :class:`CompositionIR` from a v2 spec plus user hints.

    Args:
        spec: style spec v2.
        mode: "dating" / "cv" / "social" — same value used by the
            existing ``_build_mode_prompt`` for document-style checks.
        change_instruction: scene-independent opener (e.g. "Change the
            background and clothing of the person in the reference
            photo."). The caller picks it based on mode / style so we
            can share ``_dating_social_change_instruction`` across v1
            and v2 paths.
        input_hints: user selections from "Другой вариант" modal.
            May be None.
        framing: "portrait" / "half_body" / "full_body" or None.
        gender: "male" / "female". Reserved for future
            gender-specific clothing phrasing; currently unused for v2
            since ``ClothingSlot.default`` is gender-neutral.
        strict: when True, user hints are validated against per-channel
            whitelists. When False (used for curated ``StyleVariant``s)
            user hints are trusted as-is.
        is_document: True for CV document styles; the wrapper replaces
            the quality tail entirely with ``DOC_PRESERVE`` / ``DOC_QUALITY``.
    """
    hints = dict(input_hints or {})
    substitutions: list[dict[str, str]] = []

    # style-schema-v2 migration PR2 — opt in to VariationEngineV2 when
    # the flag is on. Produces structurally richer output (separated
    # weather / time_of_day / season channels) while keeping the IR
    # shape identical so downstream wrappers do not branch.
    if _variation_engine_v2_enabled():
        from src.prompts.variation_engine_v2 import apply_variation_v2

        vr = apply_variation_v2(
            spec,
            hints,
            strict=strict,
            gender=gender,
            substitutions=substitutions,
            rng=rng,
        )
        scene_text = vr.scene
        if vr.time_of_day:
            scene_text = f"{scene_text}, {vr.time_of_day}" if scene_text else vr.time_of_day
        if vr.season:
            scene_text = f"{scene_text}, {vr.season}" if scene_text else vr.season
        framing_line, framing_requested = _resolve_framing_line(spec, framing)
        return CompositionIR(
            mode=mode,
            style_key=spec.key,
            change_instruction=change_instruction,
            scene=scene_text,
            lighting=vr.lighting,
            weather=vr.weather,
            clothing=vr.clothing,
            expression=spec.expression,
            framing_line=framing_line,
            quality_identity_base=spec.quality_identity.base,
            per_model_tail_map=dict(spec.quality_identity.per_model_tail),
            is_document=is_document,
            framing_requested=framing_requested,
            substitutions=substitutions,
        )

    scene = _resolve_scene(
        spec, hints, strict=strict, substitutions=substitutions, rng=rng,
    )
    lighting = _resolve_lighting(
        spec, hints, strict=strict, substitutions=substitutions, rng=rng,
    )
    weather = _resolve_weather(
        spec, hints, strict=strict, substitutions=substitutions, rng=rng,
    )
    clothing = _resolve_clothing(
        spec,
        hints,
        strict=strict,
        gender=gender,
        substitutions=substitutions,
        rng=rng,
    )
    framing_line, framing_requested = _resolve_framing_line(spec, framing)

    return CompositionIR(
        mode=mode,
        style_key=spec.key,
        change_instruction=change_instruction,
        scene=scene,
        lighting=lighting,
        weather=weather,
        clothing=clothing,
        expression=spec.expression,
        framing_line=framing_line,
        quality_identity_base=spec.quality_identity.base,
        per_model_tail_map=dict(spec.quality_identity.per_model_tail),
        is_document=is_document,
        framing_requested=framing_requested,
        substitutions=substitutions,
    )
