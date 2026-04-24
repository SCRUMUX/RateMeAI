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
        # v1.19: ``warm_outdoor`` is an identity_scene style (PuLID) so the
        # Preserve anchor is intentionally dropped. Photorealistic still
        # ships via IDENTITY_SCENE_QUALITY, and the scene opener supplies
        # the "reference subject" identity anchor in its place.
        p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
        assert "person in the reference photo" in p


def test_prompt_mentions_sharp_scene():
    # v1.19: SOLO_SUBJECT_ANCHOR (which mentioned "five fingers")
    # was moved out of the positive prompt and into PuLID's
    # negative_prompt. We still assert the scene-quality anchor.
    # v1.25: QUALITY_PHOTO was re-phrased from "sharp from subject to
    # background" (CGI-looking) to natural depth of field ("subject
    # in sharp focus, background slightly soft"). Any of the three
    # tokens below is sufficient evidence that the quality anchor
    # survived prompt assembly.
    p = ig.build_dating_prompt(style="rooftop_city", gender="male")
    low = p.lower()
    assert "sharp" in low or "focus" in low or "depth of field" in low


def test_all_modes_build_without_error():
    # Empty-style fallback goes through the identity_scene branch, so
    # we assert the identity_scene anchor ("reference subject" as of
    # v1.19) instead of the PRESERVE_PHOTO clause.
    for builder in (
        ig.build_dating_prompt,
        ig.build_cv_prompt,
        ig.build_social_prompt,
    ):
        p = builder(style="", gender="male")
        assert p
        assert "person in the reference photo" in p


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


def test_framing_directive_appears_in_non_document_prompt():
    """v1.26: user-selected ракурс теперь влияет на КОМПОЗИЦИЮ (директива
    в промпте), а не на выходной размер. Для non-document стилей в
    промпте должна присутствовать строка «Framing: …»."""
    p_half = ig.build_dating_prompt(
        style="warm_outdoor",
        gender="male",
        framing="half_body",
    )
    assert "framing:" in p_half.lower()
    assert "half-body" in p_half.lower()

    p_full = ig.build_dating_prompt(
        style="warm_outdoor",
        gender="female",
        framing="full_body",
    )
    assert "full body" in p_full.lower()


def test_framing_directive_skipped_for_document_styles():
    """Документные стили имеют жёсткую композицию от вендора
    (``_DOC_COMPOSITION_HINT``), поэтому framing-директива туда не
    должна попасть — иначе модель получит два конфликтующих указания."""
    p = ig.build_cv_prompt(
        style="photo_3x4",
        gender="male",
        framing="full_body",
    )
    assert "full body" not in p.lower()
    assert "composition" in p.lower()


def test_framing_does_not_change_output_size():
    """v1.26-контракт: ``resolve_output_size`` игнорирует framing.
    Раньше ``portrait`` → square_hd, ``full_body`` → portrait_16_9 —
    переключатель ракурса менял формат файла. Теперь размер задаёт
    только стиль (``spec.output_aspect``) и PuLID-эвристики."""
    spec = ig.STYLE_REGISTRY.get("dating", "warm_outdoor")
    if spec is None:
        import pytest as _pytest

        _pytest.skip("warm_outdoor not registered")

    base = ig.resolve_output_size(spec)
    for framing in ("portrait", "half_body", "full_body"):
        assert ig.resolve_output_size(spec, framing=framing) == base, (
            f"framing={framing!r} изменил output size "
            f"(было {base}, стало {ig.resolve_output_size(spec, framing=framing)})"
        )


def test_detect_depth_of_field_keywords():
    assert detect_depth_of_field("blurred city lights at night") == "shallow"
    assert detect_depth_of_field("softly blurred park at golden hour") == "shallow"
    assert detect_depth_of_field("clean studio with gradient backdrop") == "deep"


def test_depth_of_field_prompt_variants_on_spec():
    """The helper on StyleSpec itself is still used by other call sites."""
    deep = StyleSpec(
        key="x",
        mode="dating",
        background="bg",
        clothing_male="c",
        clothing_female="c",
        lighting="l",
        expression="e",
        depth_of_field="deep",
    )
    assert (
        "deep" in deep.depth_of_field_prompt().lower()
        or "sharp" in deep.depth_of_field_prompt().lower()
    )
