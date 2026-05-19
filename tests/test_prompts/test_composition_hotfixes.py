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


# ---------- v1.69 fuzzy duplicate guard -----------------------------------
#
# Regression test for the corporate / boardroom / video_call duplicate
# scene bug: when ``trigger_pool[0]`` and ``scene_anchor`` describe the
# same location, and the slot sampler picks a SHORTER ``override`` for
# the scene, the legacy substring check misses the duplicate and the
# trigger gets appended — producing two near-identical landscape
# descriptions in the early-attention slot of the prompt. The fuzzy
# token-overlap guard introduced in v1.69 short-circuits that case.


def test_ensure_trigger_skipped_when_scene_already_carries_meaning():
    """Corporate-style regression: override scene + identical-meaning
    trigger should NOT produce a duplicate."""
    scene = "modern corner office with floor-to-ceiling windows"
    trigger = (
        "modern corner office, floor-to-ceiling windows with diffused "
        "daylight, neutral beige wall, clean minimalist interior"
    )
    out = _ensure_trigger_in_scene(scene, trigger)
    # Trigger must NOT be appended — overlap of content tokens is well
    # above 0.5, so the scene is treated as already carrying it.
    assert out == scene
    # Doubly check: the heavy noun "office" appears at most once.
    assert out.lower().count("office") == 1


def test_ensure_trigger_still_appends_when_overlap_is_low():
    """Mirror-aesthetic regression: the short ``mirror`` trigger and a
    generic room scene have NO content-token overlap — the trigger
    must still be appended (legacy behaviour preserved)."""
    out = _ensure_trigger_in_scene("clean modern minimalist room", "mirror")
    assert "mirror" in out.lower()
    # The legacy comma-append format must be preserved.
    assert out.endswith("mirror")


def test_ensure_trigger_idempotent_when_trigger_is_substring():
    """The legacy substring fast-path must still beat the fuzzy
    check — if the trigger appears verbatim in the scene, no append
    happens regardless of token overlap."""
    out = _ensure_trigger_in_scene(
        "wide cobblestoned plaza in front of the Eiffel Tower at golden hour",
        "Eiffel Tower",
    )
    assert out == "wide cobblestoned plaza in front of the Eiffel Tower at golden hour"


def test_ensure_trigger_fuzzy_threshold_is_50_percent():
    """Sanity guard: a trigger that has no overlapping content tokens
    with the scene must STILL be appended (overlap = 0)."""
    scene = "neutral beige wall, clean minimalist interior"
    trigger = "modern corner office with floor-to-ceiling windows"
    out = _ensure_trigger_in_scene(scene, trigger)
    # Trigger appended because the content-token sets are disjoint —
    # the scene only carries wall/interior nouns, the trigger carries
    # office/windows nouns, so neither subset nor coverage triggers.
    assert out.endswith(trigger)


def test_ensure_trigger_short_overlap_does_not_block_append():
    """Short-trigger regression: a 2-word trigger that happens to
    share one noun with a longer scene must STILL be appended — the
    fuzzy guard requires BOTH sides to carry ≥ 3 content tokens
    before the symmetric overlap rule (3b) engages, otherwise it
    would clobber legitimate keyword triggers like ``city street``."""
    scene = "busy NYC street at golden hour with neon signs"
    trigger = "city street"
    out = _ensure_trigger_in_scene(scene, trigger)
    assert out.endswith(trigger)


def test_ensure_trigger_subset_rule_independent_of_size():
    """Subset rule (3a): trigger content tokens that form a subset of
    the scene content tokens count as 'already carried' regardless of
    relative size — guards the symmetric case where the trigger is the
    shorter of the two and is NOT a literal substring (so the legacy
    fast path can't catch it)."""
    # Re-ordered phrasing means "modern corner office" is not a
    # contiguous substring of ``scene`` — only the fuzzy subset check
    # can catch this.
    scene = "spacious office with floor-to-ceiling windows in a modern corner of the tower"
    trigger = "modern corner office"
    assert trigger not in scene  # sanity: substring fast path must miss
    out = _ensure_trigger_in_scene(scene, trigger)
    # Trigger content tokens are a subset of scene content tokens —
    # the duplicate guard must skip the append.
    assert out == scene


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
