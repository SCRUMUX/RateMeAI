"""Cross-channel coherence tests (1.32.1).

These tests pin the contract of :func:`apply_coherence` in
:mod:`src.prompts.slot_sampler`:

1. When :class:`CoherenceRule` matches the rolled season, clothing
   default is replaced with the rule's per-gender override.
2. ``override > coherence > default`` precedence — a user pin
   always wins over a coherence-driven swap.
3. Ambient filter constraints re-roll the value from the filter
   when the originally-rolled value violates the constraint.
4. The substitution log records each coherence patch with the
   ``coherence_<channel>`` channel naming convention so the executor
   can render a different transparency notice than the soft-
   substitute case.
5. When no rule matches the rolled season (or season is empty), the
   sampler emits the same output as it would without coherence —
   strictly opt-in semantics.
"""

from __future__ import annotations

from src.prompts.slot_sampler import sample
from src.prompts.style_schema_v3 import (
    AmbientPools,
    CoherenceRule,
    StyleSpecV3,
)
from src.prompts.style_schema_v2 import ClothingSlot, QualityBlock


def _spec_yacht_with_winter_pool() -> StyleSpecV3:
    """A constructed spec that mirrors the audit's winter↔linen
    conflict — the season pool still has winter (we deliberately
    keep it for the test), and the default clothing is the
    summer-coded "white linen" string. The coherence rule swaps
    clothing to a warm-coat variant when winter is rolled."""
    return StyleSpecV3(
        key="yacht_test",
        mode="dating",
        trigger_pool=("luxury yacht deck",),
        scene_anchor="luxury yacht deck overlooking open sea",
        clothing=ClothingSlot(
            default={
                "male": "white linen shirt unbuttoned, navy shorts, deck shoes",
                "female": "white linen blouse, navy shorts, deck shoes",
                "neutral": "white linen, navy shorts, deck shoes",
            },
            allowed=(),
        ),
        ambient=AmbientPools(
            season=("winter",),  # force winter for the test
            lighting=("warm cinematic", "soft golden"),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
        coherence=(
            CoherenceRule(
                season="winter",
                clothing_override={
                    "male": "warm wool coat, knit sweater, dark trousers, leather boots",
                    "female": "warm wool coat, knit top, dark trousers, leather boots",
                    "neutral": "warm wool coat, knit layers, dark trousers, leather boots",
                },
            ),
        ),
    )


def _spec_ski_with_summer_pool() -> StyleSpecV3:
    """Mirror image — ski scenario with summer rolled. Coherence rule
    swaps the default snow-boot ensemble for a thermal training kit
    when the user gets a summer roll."""
    return StyleSpecV3(
        key="ski_test",
        mode="dating",
        trigger_pool=("alpine ski slope",),
        scene_anchor="snowy alpine ski slope panorama",
        clothing=ClothingSlot(
            default={
                "male": "ski jacket, snow pants, snow boots, ski goggles in hand",
                "female": "ski jacket, snow pants, snow boots, ski goggles in hand",
                "neutral": "ski jacket, snow pants, snow boots, ski goggles in hand",
            },
            allowed=(),
        ),
        ambient=AmbientPools(
            season=("summer",),
            lighting=("warm cinematic", "soft golden"),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
        coherence=(
            CoherenceRule(
                season="summer",
                clothing_override={
                    "male": "lightweight thermal training top, fitted training trousers, hiking boots",
                    "female": "lightweight thermal training top, fitted training trousers, hiking boots",
                    "neutral": "lightweight thermal training top, fitted training trousers, hiking boots",
                },
            ),
        ),
    )


def _spec_with_lighting_filter() -> StyleSpecV3:
    """Spec where the winter rule constrains lighting to a
    season-coherent subset. Used to verify the filter re-roll path."""
    return StyleSpecV3(
        key="city_test",
        mode="social",
        trigger_pool=("urban landmark",),
        scene_anchor="urban landmark plaza",
        clothing=ClothingSlot(
            default={"male": "smart casual", "female": "smart casual", "neutral": "smart casual"},
            allowed=(),
        ),
        ambient=AmbientPools(
            season=("winter",),
            lighting=("warm cinematic", "soft golden", "blue hour", "neon nightscape"),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
        coherence=(
            CoherenceRule(
                season="winter",
                lighting_filter=("blue hour", "soft overcast"),
            ),
        ),
    )


# ---------- coherence: clothing override fires on matching season -------


def test_coherence_swaps_summer_clothing_for_winter_rule():
    """yacht + winter must NOT keep the summer linen default."""
    spec = _spec_yacht_with_winter_pool()
    rolled = sample(spec, input_hints={}, seed=0, gender="male")
    assert rolled.season == "winter"
    assert "linen" not in rolled.clothing.lower()
    assert "wool" in rolled.clothing.lower()


def test_coherence_swaps_winter_clothing_for_summer_rule():
    """ski + summer must NOT keep snow boots."""
    spec = _spec_ski_with_summer_pool()
    rolled = sample(spec, input_hints={}, seed=0, gender="male")
    assert rolled.season == "summer"
    assert "snow boots" not in rolled.clothing.lower()
    assert "thermal training" in rolled.clothing.lower()


def test_coherence_records_clothing_substitution():
    """The swap must show up in ``substitutions`` with the
    ``coherence_clothing`` channel name."""
    spec = _spec_yacht_with_winter_pool()
    rolled = sample(spec, input_hints={}, seed=1, gender="male")
    sub_channels = [s["channel"] for s in rolled.substitutions]
    assert "coherence_clothing" in sub_channels


# ---------- precedence: user override > coherence > default -------------


def test_user_clothing_override_beats_coherence_swap():
    """When the user pins clothing, the coherence rule must not
    rewrite it — even if the pinned value is summer-coded and the
    season rolled is winter."""
    spec = _spec_yacht_with_winter_pool()
    rolled = sample(
        spec,
        input_hints={"clothing_override": "white linen shirt and navy shorts"},
        seed=0,
        gender="male",
    )
    assert rolled.season == "winter"
    # User pin wins — clothing keeps the literal value.
    assert "linen" in rolled.clothing.lower()
    # And no coherence_clothing entry should appear.
    assert all(
        s["channel"] != "coherence_clothing" for s in rolled.substitutions
    )


def test_coherence_falls_through_to_default_when_no_rule_matches():
    """If the rolled season has no matching rule, clothing keeps
    its default — strictly opt-in semantics, no surprise rewrites."""
    # Same yacht spec but force season=summer (no rule for summer)
    spec = StyleSpecV3(
        key="yacht_test_2",
        mode="dating",
        trigger_pool=("luxury yacht deck",),
        scene_anchor="luxury yacht deck overlooking open sea",
        clothing=ClothingSlot(
            default={"male": "linen shirt", "female": "linen blouse", "neutral": "linen"},
            allowed=(),
        ),
        ambient=AmbientPools(
            season=("summer",),
            lighting=("warm cinematic",),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
        coherence=(
            CoherenceRule(
                season="winter",
                clothing_override={"male": "wool coat", "female": "wool coat", "neutral": "wool coat"},
            ),
        ),
    )
    rolled = sample(spec, input_hints={}, seed=0, gender="male")
    assert rolled.season == "summer"
    assert rolled.clothing == "linen shirt"
    assert all(
        not s["channel"].startswith("coherence_") for s in rolled.substitutions
    )


# ---------- ambient filter re-rolls -------------------------------------


def test_coherence_lighting_filter_rerolls_off_filter_value():
    """When the rolled lighting is not in the rule's filter, the
    sampler re-rolls from the filter using the same RNG."""
    spec = _spec_with_lighting_filter()
    rolled = sample(spec, input_hints={}, seed=0, gender="male")
    assert rolled.season == "winter"
    assert rolled.lighting in ("blue hour", "soft overcast")


def test_coherence_lighting_filter_keeps_in_filter_value():
    """When the original roll is already in the filter, the sampler
    leaves it alone — no spurious substitution log entry."""
    spec = StyleSpecV3(
        key="city_test_2",
        mode="social",
        trigger_pool=("urban landmark",),
        scene_anchor="urban landmark plaza",
        clothing=ClothingSlot(
            default={"male": "smart", "female": "smart", "neutral": "smart"},
            allowed=(),
        ),
        ambient=AmbientPools(
            season=("winter",),
            lighting=("blue hour",),  # only one option, always picked
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
        coherence=(
            CoherenceRule(
                season="winter",
                lighting_filter=("blue hour", "soft overcast"),
            ),
        ),
    )
    rolled = sample(spec, input_hints={}, seed=0, gender="male")
    assert rolled.lighting == "blue hour"
    assert all(
        s["channel"] != "coherence_lighting" for s in rolled.substitutions
    )


def test_coherence_lighting_filter_respects_user_pin():
    """User pin on lighting beats the coherence filter: even when
    the pinned value violates the filter, the rule does not touch it."""
    spec = _spec_with_lighting_filter()
    rolled = sample(
        spec,
        input_hints={"lighting": "warm cinematic"},
        seed=0,
        gender="male",
    )
    assert rolled.lighting == "warm cinematic"
    assert all(
        s["channel"] != "coherence_lighting" for s in rolled.substitutions
    )


# ---------- determinism with coherence ----------------------------------


def test_coherence_keeps_seeded_determinism():
    """Coherence must not break the seed → output contract."""
    spec = _spec_yacht_with_winter_pool()
    a = sample(spec, input_hints={}, seed=99, gender="male")
    b = sample(spec, input_hints={}, seed=99, gender="male")
    assert a == b
