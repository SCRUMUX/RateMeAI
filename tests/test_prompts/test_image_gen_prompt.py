"""Snapshot-style tests for the refactored image-generation prompt builder.

These tests do not assert exact byte strings (which would be brittle across
prompt tweaks) — they assert the structural invariants introduced by the
"single-call-quality-hardening" plan:

  - sectioned [CHANGE] / [PRESERVE] / [QUALITY] layout
  - HAIR_ANCHOR and COMPOSITION_ANCHOR always present in PRESERVE
  - BACKGROUND_FOCUS no longer used (conflict with shallow-DoF styles)
  - conditional injections are triggered by input quality hints
  - depth_of_field drives the QUALITY block
"""
from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts.style_spec import StyleSpec, detect_depth_of_field


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def test_prompt_has_three_sections():
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "[CHANGE]" in p
    assert "[PRESERVE]" in p
    assert "[QUALITY]" in p
    # Order must be CHANGE -> PRESERVE -> QUALITY
    assert p.index("[CHANGE]") < p.index("[PRESERVE]") < p.index("[QUALITY]")


def test_prompt_contains_hair_and_composition_anchors():
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "HAIR:" in p
    assert "COMPOSITION:" in p


def test_background_focus_anchor_is_retired():
    """The old 'BACKGROUND FOCUS' blanket anchor must be gone — it conflicted
    with styles that explicitly want shallow DoF / bokeh."""
    p = ig.build_dating_prompt(style="rooftop_city", gender="male")
    assert "BACKGROUND FOCUS" not in p


def test_all_modes_build_without_error():
    for builder in (
        ig.build_dating_prompt,
        ig.build_cv_prompt,
        ig.build_social_prompt,
    ):
        p = builder(style="", gender="male")
        assert "[CHANGE]" in p


def test_document_style_still_builds():
    p = ig.build_cv_prompt(style="passport_rf", gender="female")
    assert "[PRESERVE]" in p
    # ID-style headshot must mention the neutral backdrop requirement.
    assert "neutral" in p.lower()


# ---------------------------------------------------------------------------
# Conditional injections from input quality hints
# ---------------------------------------------------------------------------


def test_small_face_hint_injects_small_face_protection():
    hints = {"face_area_ratio": 0.06, "yaw": 0, "hair_bg_contrast": 0.5}
    p = ig.build_dating_prompt(
        style="warm_outdoor", gender="male", input_hints=hints,
    )
    assert ig.SMALL_FACE_PROTECTION in p


def test_low_hair_contrast_injects_strong_hair_anchor():
    hints = {"face_area_ratio": 0.4, "yaw": 0, "hair_bg_contrast": 0.02}
    p = ig.build_dating_prompt(
        style="warm_outdoor", gender="male", input_hints=hints,
    )
    assert ig.HAIR_BG_STRONG in p


def test_non_frontal_injects_hint():
    hints = {"face_area_ratio": 0.4, "yaw": 35.0, "hair_bg_contrast": 0.5}
    p = ig.build_social_prompt(
        style="", gender="male", input_hints=hints,
    )
    assert ig.NON_FRONTAL_HINT in p


def test_clean_hints_injects_nothing_extra():
    hints = {"face_area_ratio": 0.25, "yaw": 0, "hair_bg_contrast": 0.4}
    p = ig.build_dating_prompt(
        style="warm_outdoor", gender="male", input_hints=hints,
    )
    assert ig.SMALL_FACE_PROTECTION not in p
    assert ig.NON_FRONTAL_HINT not in p


# ---------------------------------------------------------------------------
# depth_of_field
# ---------------------------------------------------------------------------


def test_detect_depth_of_field_keywords():
    assert detect_depth_of_field("blurred city lights at night") == "shallow"
    assert detect_depth_of_field("softly blurred park at golden hour") == "shallow"
    assert detect_depth_of_field("clean studio with gradient backdrop") == "deep"


def test_depth_of_field_prompt_variants():
    deep = StyleSpec(
        key="x", mode="dating",
        background="bg", clothing_male="c", clothing_female="c",
        lighting="l", expression="e",
        depth_of_field="deep",
    )
    shallow = StyleSpec(
        key="y", mode="dating",
        background="bg", clothing_male="c", clothing_female="c",
        lighting="l", expression="e",
        depth_of_field="shallow",
    )
    assert "deep depth of field" in deep.depth_of_field_prompt()
    assert "shallow depth of field" in shallow.depth_of_field_prompt()
