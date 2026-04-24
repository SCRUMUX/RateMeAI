"""Variation engine v2 — separated channels, model-evident knobs.

PR2 of the style-schema-v2 migration. Replaces the legacy
:class:`src.prompts.variation_engine.VariationEngine` semantics where
"weather" values were smuggled through the ``lighting`` whitelist.

Channels handled here:

- ``lighting`` — soft / warm / cool / golden-hour / ...
- ``weather`` — clear / overcast / rain / snow / ... (enabled only
  when :attr:`StyleSpecV2.weather.enabled`)
- ``time_of_day`` — morning / afternoon / evening / night
- ``season`` — spring / summer / autumn / winter
- ``background_type`` — sub-location or override from the user

The legacy engine is left untouched; this module is additive. It is
consulted only when :attr:`settings.variation_engine_v2_enabled` is on
AND the caller is already on the v2 prompt path (executor gates both).

The public surface has two entry points:

- :func:`apply_variation_v2` — mirrors the v1 ``apply_variation`` role
  but splits channels cleanly and returns a structured tuple the
  composition builder can consume without re-parsing strings.
- :func:`generate_next_variant_hints` — produces the input_hints dict
  for the next "Другой вариант" press, cycling through available
  knobs without repeating the last choice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Sequence

from src.prompts.style_schema_v2 import StyleSpecV2


# Per-channel default whitelists — used only when a style leaves the
# slot empty AND opts in via a positive policy (e.g. weather.enabled=True
# with weather.allowed=()). We keep these small so a careless style
# author doesn't accidentally expose the full vocabulary; the style's
# own whitelist always wins.
_DEFAULT_WEATHER = ("clear", "overcast", "rain", "snow", "fog")
_DEFAULT_TIME_OF_DAY = ("morning", "afternoon", "evening", "night", "golden hour")
_DEFAULT_SEASON = ("spring", "summer", "autumn", "winter")


@dataclass(frozen=True)
class VariationResult:
    """Structured return value — consumed by :class:`CompositionIR`."""

    scene: str
    lighting: str = ""
    weather: str = ""
    time_of_day: str = ""
    season: str = ""
    clothing: str = ""


def _whitelist(spec: StyleSpecV2, channel: str) -> tuple[str, ...]:
    raw = spec.context_slots.get(channel, ())
    return tuple(raw)


def _pick(value: str, whitelist: Sequence[str], strict: bool) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if strict and whitelist and value not in whitelist:
        return ""
    return value


def apply_variation_v2(
    spec: StyleSpecV2,
    user_input: dict[str, Any] | None,
    *,
    strict: bool = True,
) -> VariationResult:
    """Build a :class:`VariationResult` from a v2 spec + user hints.

    Unlike the v1 engine, weather does NOT go through the lighting
    whitelist. Time-of-day and season are first-class. Clothing and
    scene overrides honour the lock level on the background slot.
    """
    hints = dict(user_input or {})

    # Lighting — optional per-channel override (style whitelist must
    # allow the value when strict=True).
    lighting = _pick(
        str(hints.get("lighting") or ""),
        _whitelist(spec, "lighting"),
        strict=strict,
    )

    # Weather — honours the dedicated weather policy. Empty allowed
    # tuple combined with enabled=True falls back to _DEFAULT_WEATHER
    # so newly authored styles can opt in with a single flag flip.
    weather = ""
    if spec.weather.enabled:
        allowed = spec.weather.allowed or _DEFAULT_WEATHER
        weather = _pick(str(hints.get("weather") or ""), allowed, strict=strict)

    # Time-of-day — defaults are permissive because every style has
    # some notion of "morning vs evening"; authors can narrow it.
    tod_allowed = _whitelist(spec, "time_of_day") or _DEFAULT_TIME_OF_DAY
    time_of_day = _pick(
        str(hints.get("time_of_day") or ""), tod_allowed, strict=strict
    )

    # Season — explicit opt-in. If the style doesn't declare a season
    # slot we keep it empty to avoid "winter at golden hour in Bahamas".
    season_allowed = _whitelist(spec, "season")
    season = _pick(
        str(hints.get("season") or ""),
        season_allowed,
        strict=strict,
    ) if season_allowed else ""

    # Scene override — respects the background lock level.
    from src.prompts.style_schema_v2 import BackgroundLockLevel

    scene = spec.background.base
    override = str(hints.get("scene_override") or "").strip()
    sub_location = str(hints.get("sub_location") or hints.get("background_type") or "").strip()
    if spec.background.lock == BackgroundLockLevel.SEMI and sub_location:
        if not strict or sub_location in spec.background.overrides_allowed:
            scene = f"{sub_location} in {scene}" if scene else sub_location
    elif spec.background.lock == BackgroundLockLevel.FLEXIBLE and override:
        if not strict or override in spec.background.overrides_allowed:
            scene = override

    # Clothing — whitelist is consulted in strict mode.
    clothing = spec.clothing.default
    clothing_override = str(hints.get("clothing_override") or "").strip()
    if clothing_override:
        if not strict or clothing_override in spec.clothing.allowed:
            clothing = clothing_override

    return VariationResult(
        scene=scene,
        lighting=lighting,
        weather=weather,
        time_of_day=time_of_day,
        season=season,
        clothing=clothing,
    )


def _collect_available_knobs(
    spec: StyleSpecV2,
) -> dict[str, tuple[str, ...]]:
    """Return {channel: whitelist} for channels the user may actually
    override on this style. Channels with empty whitelists are
    skipped so "Другой вариант" never proposes an empty pick.
    """
    knobs: dict[str, tuple[str, ...]] = {}

    lighting = _whitelist(spec, "lighting")
    if lighting:
        knobs["lighting"] = lighting

    if spec.weather.enabled and spec.weather.allowed:
        knobs["weather"] = tuple(spec.weather.allowed)

    tod = _whitelist(spec, "time_of_day")
    if tod:
        knobs["time_of_day"] = tod

    season = _whitelist(spec, "season")
    if season:
        knobs["season"] = season

    if spec.clothing.allowed:
        knobs["clothing_override"] = tuple(spec.clothing.allowed)

    if spec.background.overrides_allowed:
        # Expose under the user-visible channel name the frontend
        # already knows. Kept separate from ``sub_location`` here so
        # flexible and semi-locked styles can both be driven by this.
        knobs["background_type"] = tuple(spec.background.overrides_allowed)

    return knobs


def generate_next_variant_hints(
    spec: StyleSpecV2,
    *,
    history: list[dict[str, Any]] | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Produce the next "Другой вариант" hints dict.

    Strategy: pick an available channel that the user has not used in
    the most recent history entry; within that channel, pick a value
    that is not equal to the last value used on it. Falls back to a
    random pick when no previous state exists.

    Returns an empty dict when the style exposes no knobs at all
    (truly locked styles — documents, for example).
    """
    rng = rng or random.Random()
    history = list(history or [])
    knobs = _collect_available_knobs(spec)
    if not knobs:
        return {}

    last = history[-1] if history else {}
    # Prefer channels the user didn't touch last time; ordering is
    # deterministic only within a single call (Python 3.7+ preserves
    # dict insertion order, and we shuffle the preference list).
    preferred_channels = [c for c in knobs if c not in last]
    fallback_channels = [c for c in knobs if c in last]

    rng.shuffle(preferred_channels)
    rng.shuffle(fallback_channels)
    ordered_channels = preferred_channels + fallback_channels

    for channel in ordered_channels:
        options = list(knobs[channel])
        last_value = last.get(channel)
        if last_value and last_value in options and len(options) > 1:
            options.remove(last_value)
        if not options:
            continue
        return {channel: rng.choice(options)}

    return {}
