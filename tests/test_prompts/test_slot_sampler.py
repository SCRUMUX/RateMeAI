"""Stage 1 (prompt-pipeline-overhaul): SlotSampler unit tests.

The sampler is the heart of the v3 prompt path. It takes a
:class:`StyleSpecV3` plus user hints plus an optional seed and rolls
concrete values for every channel. These tests guard four contracts:

1. **Determinism via seed.** ``(spec, hints, seed)`` always returns
   the same :class:`ResolvedSlots`.
2. **Trigger is non-empty and from the pool.** The schema enforces a
   non-empty pool; the sampler enforces that the resolved trigger
   always comes from it (or from a user pin).
3. **Random pool pick on empty hint.** Channels with a non-empty
   pool always get a value rolled, even when the user said nothing.
4. **User pin wins; out-of-pool gets soft-substituted.** Pinned
   values are surfaced verbatim; off-pool pins land in the
   substitutions log without being silently dropped.

Diversity properties (e.g. "10 random seeds produce >=80% unique
slot tuples") are asserted in a smaller dedicated test that picks
non-trivial pool sizes.
"""

from __future__ import annotations

import random

import pytest

from src.prompts.slot_sampler import sample
from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    ClothingSlot,
    QualityBlock,
)
from src.prompts.style_schema_v3 import (
    AmbientPools,
    StyleSpecV3,
)


def _spec(
    *,
    trigger_pool: tuple[str, ...] = ("Burj Khalifa skyline at twilight",),
    scene_anchor: str = "open-air observation terrace overlooking the Dubai skyline",
    scene_overrides: tuple[str, ...] = (),
    lighting: tuple[str, ...] = (),
    weather: tuple[str, ...] = (),
    time_of_day: tuple[str, ...] = (),
    season: tuple[str, ...] = (),
    clothing_default: str = "elevated travel outfit",
    clothing_allowed: tuple[str, ...] = (),
) -> StyleSpecV3:
    return StyleSpecV3(
        key="t",
        mode="dating",
        trigger_pool=trigger_pool,
        scene_anchor=scene_anchor,
        scene_overrides=scene_overrides,
        background_lock=BackgroundLockLevel.SEMI,
        ambient=AmbientPools(
            lighting=lighting,
            weather=weather,
            time_of_day=time_of_day,
            season=season,
        ),
        clothing=ClothingSlot(
            default={
                "male": clothing_default,
                "female": clothing_default,
                "neutral": clothing_default,
            },
            allowed=clothing_allowed,
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


# ---------- Schema invariants ------------------------------------------------


def test_empty_trigger_pool_rejected_by_schema():
    with pytest.raises(ValueError, match="trigger_pool"):
        StyleSpecV3(
            key="bad",
            mode="dating",
            trigger_pool=(),
            scene_anchor="anywhere",
            clothing=ClothingSlot(default={"neutral": "x"}, allowed=()),
            quality_identity=QualityBlock(base="", per_model_tail={}),
        )


# ---------- Determinism ------------------------------------------------------


def test_same_seed_produces_identical_resolved_slots():
    spec = _spec(
        trigger_pool=("a", "b", "c", "d"),
        lighting=("warm", "cool", "soft"),
        weather=("clear", "overcast"),
        time_of_day=("morning", "evening", "night"),
        season=("spring", "summer", "winter"),
    )
    a = sample(spec, {}, seed=42)
    b = sample(spec, {}, seed=42)
    assert a == b


def test_different_seeds_produce_diverse_outputs():
    """≥80% unique (trigger, lighting, weather, time_of_day, season)
    tuples across 50 seeds when every pool has ≥3 values."""
    spec = _spec(
        trigger_pool=("a", "b", "c", "d", "e"),
        lighting=("warm", "cool", "soft", "harsh"),
        weather=("clear", "overcast", "rain"),
        time_of_day=("morning", "noon", "evening", "night"),
        season=("spring", "summer", "autumn", "winter"),
    )
    seen: set[tuple[str, ...]] = set()
    for s in range(50):
        r = sample(spec, {}, seed=s)
        seen.add((r.trigger, r.lighting, r.weather, r.time_of_day, r.season))
    assert len(seen) / 50 >= 0.80, (
        f"Expected ≥80% unique tuples, got {len(seen)}/50"
    )


# ---------- Trigger contract -------------------------------------------------


def test_trigger_always_non_empty_and_from_pool():
    spec = _spec(trigger_pool=("alpha", "beta", "gamma"))
    for s in range(20):
        r = sample(spec, {}, seed=s)
        assert r.trigger
        assert r.trigger in spec.trigger_pool


def test_trigger_pin_honoured_when_in_pool():
    spec = _spec(trigger_pool=("alpha", "beta", "gamma"))
    r = sample(spec, {"trigger_choice": "beta"}, seed=0)
    assert r.trigger == "beta"
    assert r.user_overrides.get("trigger") == "beta"
    assert "trigger" not in r.random_picks


def test_trigger_pin_substituted_when_off_pool_strict():
    spec = _spec(trigger_pool=("alpha", "beta"))
    r = sample(spec, {"trigger_choice": "delta"}, seed=0, strict=True)
    assert r.trigger in spec.trigger_pool
    assert any(
        s["channel"] == "trigger" and s["requested"] == "delta"
        for s in r.substitutions
    )


def test_trigger_pin_accepted_when_strict_off():
    spec = _spec(trigger_pool=("alpha", "beta"))
    r = sample(spec, {"trigger_choice": "delta"}, seed=0, strict=False)
    assert r.trigger == "delta"
    assert r.substitutions == []


# ---------- Empty hint → random pool pick ----------------------------------


def test_empty_hint_rolls_from_pool_for_every_channel():
    spec = _spec(
        lighting=("warm", "cool"),
        weather=("clear", "overcast"),
        time_of_day=("morning", "evening"),
        season=("spring", "summer"),
    )
    r = sample(spec, {}, seed=1)
    assert r.lighting in spec.ambient.lighting
    assert r.weather in spec.ambient.weather
    assert r.time_of_day in spec.ambient.time_of_day
    assert r.season in spec.ambient.season
    # Every channel that rolled lands in random_picks (and not in user_overrides).
    for ch in ("lighting", "weather", "time_of_day", "season", "trigger"):
        assert ch in r.random_picks
        assert ch not in r.user_overrides


def test_empty_pool_keeps_channel_empty():
    spec = _spec(lighting=())
    r = sample(spec, {}, seed=1)
    assert r.lighting == ""


# ---------- User pin wins ----------------------------------------------------


def test_pinned_lighting_overrides_random_pick():
    spec = _spec(lighting=("warm", "cool", "soft"))
    r = sample(spec, {"lighting": "cool"}, seed=99)
    assert r.lighting == "cool"
    assert r.user_overrides.get("lighting") == "cool"
    assert "lighting" not in r.random_picks


def test_pinned_off_pool_gets_soft_substituted_strict():
    spec = _spec(lighting=("warm", "cool"))
    r = sample(spec, {"lighting": "neon"}, seed=0, strict=True)
    assert r.lighting in spec.ambient.lighting
    assert any(
        s["channel"] == "lighting" and s["requested"] == "neon"
        for s in r.substitutions
    )
    # Original user intent is preserved in the override map.
    assert r.user_overrides.get("lighting") == "neon"


def test_pinned_off_pool_passthrough_strict_false():
    spec = _spec(lighting=("warm",))
    r = sample(spec, {"lighting": "neon"}, seed=0, strict=False)
    assert r.lighting == "neon"
    assert r.substitutions == []


# ---------- Scene resolution -------------------------------------------------


def test_scene_anchor_used_when_no_overrides_and_no_hint():
    spec = _spec(scene_anchor="the dubai skyline")
    r = sample(spec, {}, seed=0)
    assert r.scene == "the dubai skyline"


def test_scene_random_pick_from_overrides_pool():
    spec = _spec(
        scene_anchor="default",
        scene_overrides=("rooftop bar", "marina promenade", "yacht deck"),
    )
    seen = set()
    for s in range(20):
        r = sample(spec, {}, seed=s)
        seen.add(r.scene)
    # Confirms the sampler reaches into the overrides pool.
    assert seen.issubset({"default"} | set(spec.scene_overrides))
    assert len(seen) >= 2


def test_scene_user_value_wins_over_pool():
    spec = _spec(
        scene_anchor="default",
        scene_overrides=("rooftop bar", "marina promenade"),
    )
    r = sample(spec, {"scene_override": "rooftop bar"}, seed=0)
    assert r.scene == "rooftop bar"
    assert r.user_overrides.get("scene") == "rooftop bar"


# ---------- Clothing ---------------------------------------------------------


def test_clothing_default_used_when_no_override():
    spec = _spec(clothing_default="suit")
    r = sample(spec, {}, seed=0, gender="male")
    assert r.clothing == "suit"


def test_clothing_override_pass_through_when_no_whitelist():
    spec = _spec(clothing_default="suit", clothing_allowed=())
    r = sample(spec, {"clothing_override": "wizard robes"}, seed=0)
    assert r.clothing == "wizard robes"


def test_clothing_override_substitutes_off_pool_strict():
    spec = _spec(
        clothing_default="suit", clothing_allowed=("polo", "sweater", "blazer")
    )
    r = sample(spec, {"clothing_override": "wizard robes"}, seed=0, strict=True)
    assert r.clothing in {"polo", "sweater", "blazer"}
    assert any(
        s["channel"] == "clothing" and s["requested"] == "wizard robes"
        for s in r.substitutions
    )


# ---------- to_dict ----------------------------------------------------------


def test_resolved_slots_to_dict_serialises_full_payload():
    spec = _spec(
        trigger_pool=("alpha",),
        lighting=("warm",),
        weather=("clear",),
    )
    r = sample(spec, {"lighting": "warm"}, seed=0)
    payload = r.to_dict()
    assert payload["trigger"] == "alpha"
    assert payload["lighting"] == "warm"
    assert payload["weather"] == "clear"
    assert payload["user_overrides"]["lighting"] == "warm"
    assert "lighting" not in payload["random_picks"]


# ---------- External rng -----------------------------------------------------


def test_explicit_rng_supersedes_seed():
    spec = _spec(trigger_pool=("a", "b", "c"))
    rng = random.Random(7)
    r = sample(spec, {}, seed=999, rng=rng)
    rng2 = random.Random(7)
    expected_trigger = rng2.choice(spec.trigger_pool)
    assert r.trigger == expected_trigger
