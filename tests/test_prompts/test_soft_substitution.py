"""Phase 3 (v1.27.3): soft substitution + IR.substitutions log.

The composition builder no longer drops user-supplied hints that fail
the per-channel whitelist. Instead it picks a random whitelist value
and records the substitution. We assert on the IR's ``substitutions``
list so the executor (and ultimately the web UI) can surface a
post-generation notice.
"""

from __future__ import annotations

import random

import pytest

from src.prompts.composition_builder import build_composition
from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    BackgroundSlot,
    ClothingSlot,
    QualityBlock,
    StyleSpecV2,
    WeatherPolicy,
)


def _spec(
    *,
    lighting_allowed: tuple[str, ...] = (),
    bg_overrides: tuple[str, ...] = (),
    clothing_allowed: tuple[str, ...] = (),
    bg_lock: BackgroundLockLevel = BackgroundLockLevel.FLEXIBLE,
    weather_enabled: bool = False,
    weather_allowed: tuple[str, ...] = (),
) -> StyleSpecV2:
    return StyleSpecV2(
        key="t",
        mode="dating",
        trigger="",
        background=BackgroundSlot(
            base="city street",
            lock=bg_lock,
            overrides_allowed=bg_overrides,
        ),
        clothing=ClothingSlot(
            default={"male": "tee", "female": "tee", "neutral": "tee"},
            allowed=clothing_allowed,
        ),
        weather=WeatherPolicy(
            enabled=weather_enabled, allowed=weather_allowed, default_na=True
        ),
        context_slots={"lighting": lighting_allowed},
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


def test_unrecognised_lighting_substituted_from_whitelist():
    spec = _spec(lighting_allowed=("warm", "cool", "soft"))
    rng = random.Random(42)

    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change.",
        input_hints={"lighting": "lasers"},
        framing=None,
        gender="male",
        strict=True,
        rng=rng,
    )

    assert ir.lighting in {"warm", "cool", "soft"}
    assert ir.substitutions, "expected a substitution record for unrecognised lighting"
    record = ir.substitutions[0]
    assert record == {
        "channel": "lighting",
        "requested": "lasers",
        "applied": ir.lighting,
    }


def test_recognised_lighting_does_not_substitute():
    spec = _spec(lighting_allowed=("warm", "cool"))
    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change.",
        input_hints={"lighting": "warm"},
        framing=None,
        gender="male",
        strict=True,
    )
    assert ir.lighting == "warm"
    assert ir.substitutions == []


def test_empty_whitelist_keeps_user_value_for_free_text_clothing():
    """Clothing channel without ``allowed`` whitelist accepts arbitrary
    user text — that is the documented free-text contract. No
    substitution is recorded."""
    spec = _spec(clothing_allowed=())
    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change.",
        input_hints={"clothing_override": "wizard robes"},
        framing=None,
        gender="male",
        strict=True,
    )
    assert ir.clothing == "wizard robes"
    assert ir.substitutions == []


def test_unrecognised_clothing_with_whitelist_substitutes():
    spec = _spec(clothing_allowed=("polo", "blazer", "sweater"))
    rng = random.Random(7)

    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change.",
        input_hints={"clothing_override": "spacesuit"},
        framing=None,
        gender="male",
        strict=True,
        rng=rng,
    )
    assert ir.clothing in {"polo", "blazer", "sweater"}
    assert any(s["channel"] == "clothing" for s in ir.substitutions)


def test_unrecognised_scene_on_semi_substitutes_within_whitelist():
    spec = _spec(
        bg_lock=BackgroundLockLevel.SEMI,
        bg_overrides=("crosswalk", "billboard alley"),
    )
    rng = random.Random(11)
    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change.",
        input_hints={"scene_override": "Эверест"},
        framing=None,
        gender="male",
        strict=True,
        rng=rng,
    )
    # SEMI prepends the chosen value to base.
    assert ir.scene.startswith(("crosswalk", "billboard alley"))
    assert any(s["channel"] == "scene" for s in ir.substitutions)


@pytest.mark.parametrize("strict", [True, False])
def test_strict_off_never_substitutes(strict):
    """variant-driven curated paths run with ``strict=False`` — they
    must trust the supplied hints and never alter them."""
    spec = _spec(lighting_allowed=("warm",))
    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change.",
        input_hints={"lighting": "neon"},
        framing=None,
        gender="male",
        strict=strict,
    )
    if strict:
        # Strict path either accepts the literal (when in whitelist) or
        # substitutes; here "neon" is not in {"warm"} so substitute.
        assert ir.lighting == "warm"
        assert ir.substitutions
    else:
        assert ir.lighting == "neon"
        assert ir.substitutions == []
