"""Structural invariants for the compact photorealistic prompt (v1.13).

The old tag-sectioned layout ([CHANGE]/[PRESERVE]/[QUALITY]) was retired
because it exceeded Reve's effective prompt budget and added no
adherence benefit. These tests lock in the new compact single-paragraph
template without tying to exact wording.
"""
from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts.style_spec import StyleSpec, detect_depth_of_field


def test_prompt_has_no_section_tags():
    """The old [CHANGE]/[PRESERVE]/[QUALITY] tags must not appear."""
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "[CHANGE]" not in p
    assert "[PRESERVE]" not in p
    assert "[QUALITY]" not in p


def test_prompt_has_preserve_and_photorealistic_anchors():
    # ``warm_outdoor`` is an identity_scene style (PuLID) so the
    # Preserve anchor is intentionally dropped. Photorealistic still
    # ships via IDENTITY_SCENE_QUALITY, and the scene opener supplies
    # the "reference person" identity anchor in its place.
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "Photorealistic" in p
    assert "reference person" in p


def test_prompt_mentions_five_fingers_and_sharp_scene():
    p = ig.build_dating_prompt(style="rooftop_city", gender="male")
    assert "five" in p.lower() and "finger" in p.lower()
    assert "sharp" in p.lower()


def test_all_modes_build_without_error():
    # Empty-style fallback goes through the identity_scene branch, so
    # we assert the identity_scene anchor "reference person" instead of
    # the PRESERVE_PHOTO clause.
    for builder in (
        ig.build_dating_prompt,
        ig.build_cv_prompt,
        ig.build_social_prompt,
    ):
        p = builder(style="", gender="male")
        assert p
        assert "reference person" in p


def test_document_style_uses_doc_template():
    p = ig.build_cv_prompt(style="passport_rf", gender="female")
    assert "ID-style headshot" in p
    lower = p.lower()
    assert "white" in lower or "neutral" in lower
    assert "[PRESERVE]" not in p


def test_document_style_includes_composition_hint():
    p = ig.build_cv_prompt(style="photo_3x4", gender="male")
    assert "Composition" in p


def test_input_hints_do_not_break_builder():
    """input_hints is kept for backwards compat; must not change length dramatically."""
    p_plain = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    p_hint = ig.build_dating_prompt(
        style="warm_outdoor",
        gender="male",
        input_hints={"face_area_ratio": 0.05, "yaw": 35.0, "hair_bg_contrast": 0.02},
    )
    assert p_plain == p_hint


def test_prompt_budget_spot_check():
    """Spot-check that the compact template stays well under the hard cap."""
    p = ig.build_dating_prompt(style="rooftop_city", gender="male")
    assert len(p) <= ig.PROMPT_MAX_LEN
    p = ig.build_cv_prompt(style="neutral", gender="male")
    assert len(p) <= ig.PROMPT_MAX_LEN
    p = ig.build_cv_prompt(style="photo_3x4", gender="female")
    assert len(p) <= ig.PROMPT_MAX_LEN


def test_step_templates_have_preserve_and_photorealistic():
    for _key, tmpl in ig.STEP_TEMPLATES.items():
        assert "Preserve" in tmpl
        assert "Photorealistic" in tmpl


def test_detect_depth_of_field_keywords():
    assert detect_depth_of_field("blurred city lights at night") == "shallow"
    assert detect_depth_of_field("softly blurred park at golden hour") == "shallow"
    assert detect_depth_of_field("clean studio with gradient backdrop") == "deep"


def test_depth_of_field_prompt_variants_on_spec():
    """The helper on StyleSpec itself is still used by other call sites."""
    deep = StyleSpec(
        key="x", mode="dating",
        background="bg", clothing_male="c", clothing_female="c",
        lighting="l", expression="e",
        depth_of_field="deep",
    )
    assert "deep" in deep.depth_of_field_prompt().lower() or "sharp" in deep.depth_of_field_prompt().lower()
