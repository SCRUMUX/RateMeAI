"""Regression and contract tests for StyleVariant content and wiring."""
from __future__ import annotations

import pytest

from src.prompts import image_gen as ig
from src.prompts.style_spec import StyleVariant, validate_style
from src.prompts.style_variants import STYLE_VARIANTS


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def _non_document_styles() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key in ig.DATING_STYLES:
        out.append(("dating", key))
    for key in ig.CV_STYLES:
        if key in ig._DOCUMENT_STYLE_KEYS:
            continue
        out.append(("cv", key))
    for key in ig.SOCIAL_STYLES:
        out.append(("social", key))
    return out


@pytest.mark.parametrize("mode,style", _non_document_styles())
def test_non_document_styles_have_at_least_four_variants(mode: str, style: str):
    spec = ig.STYLE_REGISTRY.get(mode, style)
    assert spec is not None, f"{mode}/{style}: not registered"
    assert len(spec.variants) >= 4, (
        f"{mode}/{style}: expected ≥4 variants, got {len(spec.variants)}"
    )

    ids = [v.id for v in spec.variants]
    assert len(set(ids)) == len(ids), (
        f"{mode}/{style}: variants contain duplicate ids: {ids}"
    )


def test_document_styles_have_no_variants():
    for key in ig._DOCUMENT_STYLE_KEYS:
        spec = ig.STYLE_REGISTRY.get("cv", key)
        if spec is None:
            continue
        assert spec.variants == (), (
            f"cv/{key}: document styles must not define variants"
        )


# ---------------------------------------------------------------------------
# Variant hygiene — positive framing, banned phrases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode,style", _non_document_styles())
def test_variants_pass_validate_style(mode: str, style: str):
    spec = ig.STYLE_REGISTRY.get(mode, style)
    assert spec is not None
    warnings = validate_style(spec)
    assert warnings == [], f"{mode}/{style} warnings:\n" + "\n".join(warnings)


# ---------------------------------------------------------------------------
# Prompt injection produces scene/lighting/clothing accents
# ---------------------------------------------------------------------------


def test_build_dating_prompt_includes_variant_scene_and_lighting():
    v = StyleVariant(
        id="sunrise_beach",
        scene="sandy beach near gentle ocean waves",
        lighting="warm pink-orange sunrise backlight",
        props="yoga mat on sand",
        camera="low-angle from mat",
    )
    p = ig.build_dating_prompt("yoga_outdoor", gender="male", variant=v)
    assert "sandy beach near gentle ocean waves" in p
    assert "warm pink-orange sunrise backlight" in p
    assert "yoga mat on sand" in p
    assert "low-angle from mat" in p


def test_build_dating_prompt_applies_gender_specific_clothing_accent():
    v = StyleVariant(
        id="rooftop_golden",
        scene="rooftop terrace with city view",
        lighting="warm golden-hour backlight",
        clothing_male_accent="dark fitted jeans",
        clothing_female_accent="flowing midi skirt",
    )
    p_male = ig.build_dating_prompt("warm_outdoor", gender="male", variant=v)
    p_female = ig.build_dating_prompt("warm_outdoor", gender="female", variant=v)
    assert "dark fitted jeans" in p_male
    assert "dark fitted jeans" not in p_female
    assert "flowing midi skirt" in p_female
    assert "flowing midi skirt" not in p_male


@pytest.mark.parametrize("mode,style", _non_document_styles())
def test_variant_prompts_fit_budget_and_preserve_anchors(mode: str, style: str):
    spec = ig.STYLE_REGISTRY.get(mode, style)
    assert spec is not None
    # v1.18: identity_scene styles (PuLID) omit the "Preserve the exact
    # same person" anchor — the model locks identity via the face
    # reference, and repeating the anchor hurts Lightning's sampling.
    # scene_preserve styles still ship the anchor.
    is_identity_scene = (
        getattr(spec, "generation_mode", "identity_scene")
        == "identity_scene"
    )
    for variant in spec.variants:
        for gender in ("male", "female"):
            if mode == "dating":
                prompt = ig.build_dating_prompt(style, gender=gender, variant=variant)
            elif mode == "cv":
                prompt = ig.build_cv_prompt(style, gender=gender, variant=variant)
            else:
                prompt = ig.build_social_prompt(style, gender=gender, variant=variant)
            assert len(prompt) <= ig.PROMPT_MAX_LEN, (
                f"{mode}/{style}/{variant.id}/{gender} "
                f"prompt too long: {len(prompt)}"
            )
            if is_identity_scene:
                # v1.19: scene-focused opener mentions "reference
                # subject" once. SOLO_SUBJECT_ANCHOR moved out of the
                # positive prompt into PuLID's negative_prompt.
                assert "reference subject" in prompt
            else:
                assert "Preserve the exact same person" in prompt
            assert "Photorealistic" in prompt


def test_document_style_ignores_variant_injection():
    v = StyleVariant(
        id="fake_scene",
        scene="bright marketplace with colorful fabrics",
        lighting="vivid midday sunlight",
    )
    p = ig.build_cv_prompt("passport_rf", gender="male", variant=v)
    assert "bright marketplace with colorful fabrics" not in p
    assert "vivid midday sunlight" not in p


# ---------------------------------------------------------------------------
# STYLE_VARIANTS registry shape
# ---------------------------------------------------------------------------


def test_style_variants_registry_keys_match_registered_styles():
    for (mode, key), variants in STYLE_VARIANTS.items():
        spec = ig.STYLE_REGISTRY.get(mode, key)
        assert spec is not None, f"{mode}/{key} not in registry"
        assert spec.variants == variants


def test_resolve_style_variant_returns_registered_variant():
    mode, style = "dating", "yoga_outdoor"
    spec = ig.STYLE_REGISTRY.get(mode, style)
    chosen_id = spec.variants[0].id
    resolved = ig.resolve_style_variant(mode, style, chosen_id)
    assert resolved is not None
    assert resolved.id == chosen_id


def test_resolve_style_variant_none_for_document_style():
    assert ig.resolve_style_variant("cv", "passport_rf", "anything") is None


def test_resolve_style_variant_none_for_unknown_id():
    assert ig.resolve_style_variant("dating", "yoga_outdoor", "__missing__") is None
