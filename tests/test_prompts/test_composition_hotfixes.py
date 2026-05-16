"""Stage 0 (prompt-pipeline-overhaul): hot fixes for ``CompositionIR``.

Two regressions were addressed before the v3 schema migration ships:

1. ``scene_line`` used to render "X lighting lighting" / "X weather
   weather" when the channel value already contained the noun. Authors
   wrote ``lighting="warm tungsten light"`` because the legacy v1 lights
   were location-shaped and the suffix was implicit. The new builder
   strips a duplicate noun.

2. The ``trigger`` field on :class:`StyleSpecV2` had been first-class
   data since v1.27 but never reached the final prompt: ten styles
   (mirror_aesthetic, eiffel, nyc_times_square, ...) shipped with a
   ``background.base`` that lacked the headline motif keyword. The
   composition builder now appends ``spec.trigger`` to the rendered
   scene if it is missing, so the user always sees the motif in the
   default prompt — regardless of whether they opened «Другой вариант».
"""

from __future__ import annotations

from src.prompts.composition_builder import (
    CompositionIR,
    build_composition,
    _ensure_trigger_in_scene,
    _with_suffix,
)
from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    BackgroundSlot,
    ClothingSlot,
    QualityBlock,
    StyleSpecV2,
    WeatherPolicy,
)


def _spec(*, trigger: str = "", base: str = "city street") -> StyleSpecV2:
    return StyleSpecV2(
        key="t",
        mode="dating",
        trigger=trigger,
        background=BackgroundSlot(
            base=base,
            lock=BackgroundLockLevel.FLEXIBLE,
            overrides_allowed=(),
        ),
        clothing=ClothingSlot(
            default={"male": "tee", "female": "tee", "neutral": "tee"},
            allowed=(),
        ),
        weather=WeatherPolicy(enabled=False, allowed=(), default_na=True),
        context_slots={},
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


# ---------- _with_suffix ---------------------------------------------------


def test_with_suffix_appends_when_value_lacks_noun():
    assert _with_suffix("warm", "lighting", ("lighting", "light")) == "warm lighting"


def test_with_suffix_skips_when_value_already_ends_with_noun():
    assert _with_suffix("warm tungsten light", "lighting", ("lighting", "light")) == (
        "warm tungsten light"
    )
    assert _with_suffix("soft lighting", "lighting", ("lighting", "light")) == (
        "soft lighting"
    )


def test_with_suffix_handles_trailing_punctuation():
    assert _with_suffix("rainy weather.", "weather", ("weather",)) == "rainy weather."


def test_with_suffix_returns_empty_for_blank_input():
    assert _with_suffix("", "lighting", ("lighting",)) == ""
    assert _with_suffix("   ", "lighting", ("lighting",)) == ""


def test_scene_line_narrative_lighting_no_stutter():
    """v4.1 narrative scene_line(): the "lit by X" prefix never
    duplicates an already-present "lighting" / "light" suffix in the
    channel value.
    """
    ir = CompositionIR(
        mode="dating",
        style_key="t",
        change_instruction="",
        scene="paris boulevard",
        lighting="warm tungsten light",
        weather="",
    )
    line = ir.scene_line()
    assert "lit by warm tungsten light" in line.lower()
    # No "light light" / "light lighting" stutter from the suffix
    # appender.
    assert "light lighting" not in line.lower()
    assert "lit by warm tungsten lighting" not in line.lower()


def test_scene_line_narrative_weather_during_morning():
    """v4.1: weather + time_of_day combine into a single grammatical
    fragment "during a <weather> <time_of_day>".
    """
    ir = CompositionIR(
        mode="dating",
        style_key="t",
        change_instruction="",
        scene="park",
        lighting="",
        weather="rainy",
        time_of_day="morning",
    )
    line = ir.scene_line()
    assert "during a rainy morning" in line.lower()
    assert "weather weather" not in line.lower()


def test_scene_line_narrative_full_layout():
    """v4.1: when lighting + weather + time + season are all set we
    emit a narrative sentence rather than a comma-stack.
    """
    ir = CompositionIR(
        mode="dating",
        style_key="t",
        change_instruction="",
        scene="park",
        lighting="warm",
        weather="clear",
        time_of_day="morning",
        season="autumn",
    )
    line = ir.scene_line()
    lower = line.lower()
    assert lower.startswith("park")
    assert "lit by warm" in lower
    assert "during a clear morning" in lower
    assert "in autumn" in lower


# ---------- _ensure_trigger_in_scene --------------------------------------


def test_ensure_trigger_appends_when_absent():
    out = _ensure_trigger_in_scene("clean modern minimalist room", "mirror")
    assert "mirror" in out.lower()


def test_ensure_trigger_idempotent_when_already_present():
    out = _ensure_trigger_in_scene("modern bedroom with a mirror and plants", "mirror")
    assert out == "modern bedroom with a mirror and plants"


def test_ensure_trigger_handles_empty_inputs():
    assert _ensure_trigger_in_scene("", "mirror") == "mirror"
    assert _ensure_trigger_in_scene("scene", "") == "scene"
    assert _ensure_trigger_in_scene("", "") == ""


def test_build_composition_injects_trigger_when_missing_from_base():
    """Mirrors the mirror_aesthetic regression: ``base`` says "clean
    modern minimalist room" with no mirror reference. The builder
    should append the trigger so the model sees the motif."""
    spec = _spec(
        trigger="mirror",
        base="clean modern minimalist room, indirect lighting, neutral walls",
    )
    ir = build_composition(
        spec,
        mode="social",
        change_instruction="Change the background.",
        input_hints={},
        framing=None,
        gender="male",
        strict=True,
    )
    assert "mirror" in ir.scene.lower()


def test_build_composition_keeps_trigger_already_in_base():
    spec = _spec(
        trigger="eiffel",
        base="parisian boulevard with the eiffel tower in the background",
    )
    ir = build_composition(
        spec,
        mode="dating",
        change_instruction="Change the background.",
        input_hints={},
        framing=None,
        gender="male",
        strict=True,
    )
    # No double-mention should be introduced.
    assert ir.scene.lower().count("eiffel") == 1
