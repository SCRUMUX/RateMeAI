"""Slot sampler — turns a :class:`StyleSpecV3` + user hints into
concrete :class:`ResolvedSlots`.

Stage 1 of the prompt-pipeline-overhaul. The sampler is the single
authority for "what value lands in the prompt for each axis", with the
following contract:

1. **Trigger is inviolable.** :attr:`StyleSpecV3.trigger_pool` is
   guaranteed non-empty by the schema. The sampler always rolls one
   value into :attr:`ResolvedSlots.trigger`. If the user passes an
   explicit ``trigger_choice`` hint AND that string is in the pool,
   we honour it; otherwise we fall back to a random pool pick (with
   a substitution record for traceability).

2. **Empty hint → random pool pick.** Unlike v2 (which left a slot
   empty when the user did not provide a hint), v3 always rolls a
   value when the channel's pool is non-empty. This is the core
   change requested by the user: "10 пользователей даже при первой
   генерации получают разные фото".

3. **Filled hint → respect.** When the user passes a hint and the
   value is in the pool, we use it verbatim. When the value is NOT
   in the pool (and ``strict=True``), we softly substitute from the
   pool and append a record to ``substitutions`` so the executor can
   surface a UI notice.

4. **Empty pool → empty output.** A channel with an empty pool stays
   empty in :attr:`ResolvedSlots`. The composition builder drops
   empty channels from the final prompt.

5. **Determinism via seed.** When the caller supplies an integer
   ``seed``, the sampler's :class:`random.Random` is seeded so the
   same ``(spec, hints, seed)`` triple always returns the same
   result. The executor uses this for "Improve" replay and for the
   per-attempt anti-repeat logic of "Другой вариант".

The implementation is intentionally branch-light — the same
``_resolve`` helper handles every channel.
"""

from __future__ import annotations

import random
from typing import Any

from src.prompts.style_schema_v3 import (
    AmbientPools,
    CoherenceRule,
    ResolvedSlots,
    StyleSpecV3,
)


_AMBIENT_CHANNELS: tuple[str, ...] = ("lighting", "weather", "time_of_day", "season")
_COHERENCE_FILTERED_CHANNELS: tuple[str, ...] = ("lighting", "weather", "time_of_day")


def _norm(value: Any) -> str:
    """Normalise an arbitrary input to a stripped string."""
    return str(value or "").strip()


def _resolve_channel(
    *,
    channel: str,
    pool: tuple[str, ...],
    user_value: str,
    strict: bool,
    rng: random.Random,
    random_picks: dict[str, str],
    user_overrides: dict[str, str],
    substitutions: list[dict[str, str]],
) -> str:
    """Resolve a single ambient channel.

    Returns the concrete value emitted into :class:`ResolvedSlots` and
    mutates the bookkeeping dicts so the caller can build the partition
    of "what user picked" vs "what we rolled" without a second pass.
    """
    if user_value:
        if not strict or not pool or user_value in pool:
            user_overrides[channel] = user_value
            return user_value
        # User picked something outside the pool — substitute and
        # record. The user's intent (a non-empty pin) is preserved
        # in user_overrides so the UI can show "you asked X, we used Y".
        chosen = rng.choice(pool)
        substitutions.append(
            {"channel": channel, "requested": user_value, "applied": chosen}
        )
        user_overrides[channel] = user_value
        return chosen
    if not pool:
        return ""
    chosen = rng.choice(pool)
    random_picks[channel] = chosen
    return chosen


def _resolve_trigger(
    *,
    pool: tuple[str, ...],
    user_value: str,
    strict: bool,
    rng: random.Random,
    random_picks: dict[str, str],
    user_overrides: dict[str, str],
    substitutions: list[dict[str, str]],
) -> str:
    """Resolve the trigger axis with a strict guarantee of non-empty
    output (the schema enforces ``len(pool) >= 1``).

    Mirrors :func:`_resolve_channel` but never returns ``""``.
    """
    if user_value:
        if not strict or user_value in pool:
            user_overrides["trigger"] = user_value
            return user_value
        chosen = rng.choice(pool)
        substitutions.append(
            {"channel": "trigger", "requested": user_value, "applied": chosen}
        )
        user_overrides["trigger"] = user_value
        return chosen
    chosen = rng.choice(pool)
    random_picks["trigger"] = chosen
    return chosen


def _resolve_scene(
    *,
    spec: StyleSpecV3,
    user_value: str,
    strict: bool,
    rng: random.Random,
    random_picks: dict[str, str],
    user_overrides: dict[str, str],
    substitutions: list[dict[str, str]],
) -> str:
    """Pick the scene anchor.

    Anchor preference order:

    1. User override (``scene_override`` / ``sub_location`` /
       ``background_type`` hint) — validated against ``scene_overrides``
       in strict mode.
    2. Random pick from ``scene_overrides`` when authors want diversity
       across scenes (this branch fires only when the pool is non-empty
       AND the user said nothing — same logic as ambient channels).
    3. The fixed ``scene_anchor``.

    The trigger is appended to the chosen anchor by the composition
    builder, not here.
    """
    if user_value:
        if not strict or not spec.scene_overrides or user_value in spec.scene_overrides:
            user_overrides["scene"] = user_value
            return user_value
        chosen = rng.choice(spec.scene_overrides)
        substitutions.append(
            {"channel": "scene", "requested": user_value, "applied": chosen}
        )
        user_overrides["scene"] = user_value
        return chosen
    # No user pin — when scene_overrides is non-empty, roll one of those
    # for diversity; otherwise fall back to the canonical anchor.
    # Authors who want a fixed anchor leave scene_overrides empty.
    if spec.scene_overrides:
        chosen = rng.choice(spec.scene_overrides)
        random_picks["scene"] = chosen
        return chosen
    return spec.scene_anchor


def _resolve_clothing(
    *,
    spec: StyleSpecV3,
    user_value: str,
    gender: str,
    strict: bool,
    rng: random.Random,
    random_picks: dict[str, str],
    user_overrides: dict[str, str],
    substitutions: list[dict[str, str]],
) -> str:
    """Clothing gets two layers — pinned override OR per-gender default.

    The default already accounts for gender via :meth:`ClothingSlot.text`,
    so here we only need to handle the override path.
    """
    default = spec.clothing.text(gender)
    if not user_value:
        return default
    if not strict or not spec.clothing.allowed or user_value in spec.clothing.allowed:
        user_overrides["clothing"] = user_value
        return user_value
    chosen = rng.choice(spec.clothing.allowed)
    substitutions.append(
        {"channel": "clothing", "requested": user_value, "applied": chosen}
    )
    user_overrides["clothing"] = user_value
    return chosen


def sample(
    spec: StyleSpecV3,
    input_hints: dict[str, Any] | None = None,
    *,
    seed: int | None = None,
    rng: random.Random | None = None,
    strict: bool = True,
    gender: str = "neutral",
) -> ResolvedSlots:
    """Roll concrete slot values for ``spec`` honouring ``input_hints``.

    Args:
        spec: a v3 style spec.
        input_hints: user-supplied per-channel overrides. The dict
            keys mirror the modal field names; unknown keys are
            silently ignored. ``trigger_choice`` pins the trigger
            against the pool; all other keys map 1:1 onto
            :class:`AmbientPools` channels (``lighting``, ``weather``,
            ``time_of_day``, ``season``), plus ``scene_override`` /
            ``sub_location`` / ``background_type`` for scenes and
            ``clothing_override`` for the wardrobe.
        seed: optional integer for deterministic sampling. When set,
            the sampler instantiates ``random.Random(seed)``; otherwise
            it uses ``rng`` if provided or a fresh non-deterministic
            generator.
        rng: an explicit random generator (overrides ``seed``). Use
            this when a parent caller already owns one (e.g. tests).
        strict: when True, hints that are out of pool get softly
            substituted with a substitutions log. When False, out-of-
            pool hints are accepted as-is — used by curated variants.
        gender: "male" / "female" / "neutral" — forwarded to clothing.

    Returns:
        A :class:`ResolvedSlots` with concrete picks, partitioned
        between random rolls and user overrides for downstream
        persistence + UI rendering.
    """
    hints = dict(input_hints or {})
    chooser = rng if rng is not None else random.Random(seed) if seed is not None else random.Random()

    random_picks: dict[str, str] = {}
    user_overrides: dict[str, str] = {}
    substitutions: list[dict[str, str]] = []

    trigger = _resolve_trigger(
        pool=spec.trigger_pool,
        user_value=_norm(hints.get("trigger_choice")),
        strict=strict,
        rng=chooser,
        random_picks=random_picks,
        user_overrides=user_overrides,
        substitutions=substitutions,
    )

    scene_user_value = (
        _norm(hints.get("scene_override"))
        or _norm(hints.get("sub_location"))
        or _norm(hints.get("background_type"))
    )
    scene = _resolve_scene(
        spec=spec,
        user_value=scene_user_value,
        strict=strict,
        rng=chooser,
        random_picks=random_picks,
        user_overrides=user_overrides,
        substitutions=substitutions,
    )

    ambient: dict[str, str] = {}
    pools: AmbientPools = spec.ambient
    for channel in _AMBIENT_CHANNELS:
        if not spec.is_channel_enabled(channel):
            ambient[channel] = ""
            continue
        ambient[channel] = _resolve_channel(
            channel=channel,
            pool=pools.for_channel(channel),
            user_value=_norm(hints.get(channel)),
            strict=strict,
            rng=chooser,
            random_picks=random_picks,
            user_overrides=user_overrides,
            substitutions=substitutions,
        )

    clothing = _resolve_clothing(
        spec=spec,
        user_value=_norm(hints.get("clothing_override")),
        gender=gender,
        strict=strict,
        rng=chooser,
        random_picks=random_picks,
        user_overrides=user_overrides,
        substitutions=substitutions,
    )

    # 1.32.1 — apply cross-channel coherence rules. The independent
    # sampling above gives maximum first-roll diversity; coherence
    # patches the few combinations that would be semantically
    # incoherent (e.g. winter + summer dress on a yacht).
    if spec.coherence and ambient["season"]:
        clothing, ambient = _apply_coherence(
            spec=spec,
            rolled_season=ambient["season"],
            ambient=ambient,
            clothing=clothing,
            gender=gender,
            user_overrides=user_overrides,
            random_picks=random_picks,
            substitutions=substitutions,
            rng=chooser,
        )

    return ResolvedSlots(
        trigger=trigger,
        scene=scene,
        lighting=ambient["lighting"],
        weather=ambient["weather"],
        time_of_day=ambient["time_of_day"],
        season=ambient["season"],
        clothing=clothing,
        expression=spec.expression,
        random_picks=random_picks,
        user_overrides=user_overrides,
        substitutions=substitutions,
    )


def _find_coherence_rule(
    rules: tuple[CoherenceRule, ...], season: str
) -> CoherenceRule | None:
    """Return the first rule whose season matches ``season`` (case-
    insensitive). Empty / None inputs return None."""
    if not season or not rules:
        return None
    target = season.strip().lower()
    if not target:
        return None
    for rule in rules:
        if rule.season.strip().lower() == target:
            return rule
    return None


def _apply_coherence(
    *,
    spec: StyleSpecV3,
    rolled_season: str,
    ambient: dict[str, str],
    clothing: str,
    gender: str,
    user_overrides: dict[str, str],
    random_picks: dict[str, str],
    substitutions: list[dict[str, str]],
    rng: random.Random,
) -> tuple[str, dict[str, str]]:
    """Patch the independently-sampled slots to enforce coherence.

    Mutates ``ambient`` / ``random_picks`` / ``substitutions`` in-place
    and returns ``(clothing, ambient)``. Returns the ambient dict so
    the caller can keep using a single reference; the dict is also the
    same instance it received.

    User pins (registered in ``user_overrides``) are inviolable: the
    rule never overwrites a channel the user explicitly set. The
    substitution log uses ``"coherence_<channel>"`` channel names so
    the executor can render a different transparency notice than the
    out-of-pool soft-substitute case.
    """
    rule = _find_coherence_rule(spec.coherence, rolled_season)
    if rule is None:
        return clothing, ambient

    # Clothing: only apply when user did NOT pin it. The override is
    # gender-aware; missing genders fall through to the default
    # clothing for that gender (no swap happens).
    if "clothing" not in user_overrides:
        gender_norm = gender if gender in rule.clothing_override else "neutral"
        new_clothing = rule.clothing_override.get(gender_norm, "")
        if new_clothing and new_clothing != clothing:
            substitutions.append(
                {
                    "channel": "coherence_clothing",
                    "requested": clothing,
                    "applied": new_clothing,
                }
            )
            clothing = new_clothing

    # Ambient filters: re-roll when the current value is not in the
    # filter AND the user did not pin the channel.
    filter_map: dict[str, tuple[str, ...]] = {
        "lighting": rule.lighting_filter,
        "weather": rule.weather_filter,
        "time_of_day": rule.time_of_day_filter,
    }
    for channel in _COHERENCE_FILTERED_CHANNELS:
        whitelist = filter_map[channel]
        if not whitelist:
            continue  # no constraint for this channel
        if channel in user_overrides:
            continue  # user explicitly pinned — never override
        current = ambient.get(channel, "")
        if current and current in whitelist:
            continue  # already coherent
        if not whitelist:
            continue
        # Re-roll using the same RNG to stay deterministic for a given
        # ``(spec, hints, seed)``.
        replacement = rng.choice(whitelist)
        if current != replacement:
            substitutions.append(
                {
                    "channel": f"coherence_{channel}",
                    "requested": current,
                    "applied": replacement,
                }
            )
            ambient[channel] = replacement
            random_picks[channel] = replacement

    return clothing, ambient
