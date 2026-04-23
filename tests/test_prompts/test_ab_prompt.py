"""Structural invariants for the v1.21 A/B prompt adapter.

The adapter auto-assembles the 8-block prompt layout
(Subject / Scene / Style / Lighting / Camera / Identity & Realism /
Enhancement / Output) from existing StyleSpec + StyleVariant fields.
We do NOT pin exact wording; instead we test the invariants that the
downstream models rely on:

- all 8 block labels are present in the Nano Banana wrapper
- the Camera block contains the verbatim anchor from the product spec
- the Nano Banana wrapper prepends the identity anchor
  ``Keep facial features exactly the same as the reference image.``
- the GPT Image 2 wrapper contains the ``Change:/Preserve:/Constraints:``
  triptych recommended by the fal GPT Image 2 prompting guide
- prompt length never exceeds ``settings.ab_prompt_max_len``
- gender affects the Subject block wording
- unknown modes / styles do not crash (fallback path)
"""
from __future__ import annotations

import pytest

from src.config import settings
from src.prompts.ab_prompt import (
    CAMERA_BLOCK,
    IDENTITY_BLOCK,
    ENHANCEMENT_BLOCK,
    NANO_BANANA_IDENTITY_ANCHOR,
    OUTPUT_BLOCK,
    build_structured_prompt,
)
from src.prompts.image_gen import STYLE_REGISTRY


# ----------------------------------------------------------------------
# Nano Banana wrapper
# ----------------------------------------------------------------------


def test_nano_banana_has_all_eight_block_labels():
    p = build_structured_prompt(
        mode="dating", style="warm_outdoor",
        gender="male", variant=None, model="nano_banana_2",
    )
    for label in (
        "Subject:", "Scene:", "Style:", "Lighting:",
        "Camera:", "Identity & Realism:", "Enhancement:", "Output:",
    ):
        assert label in p, f"missing block {label}: prompt was\n{p}"


def test_nano_banana_has_verbatim_camera_anchor():
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "nano_banana_2",
    )
    assert CAMERA_BLOCK in p


def test_nano_banana_has_identity_anchor():
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "nano_banana_2",
    )
    assert NANO_BANANA_IDENTITY_ANCHOR in p
    # And the fixed identity lock still follows it.
    assert IDENTITY_BLOCK in p


def test_nano_banana_has_enhancement_and_output_blocks():
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "nano_banana_2",
    )
    assert ENHANCEMENT_BLOCK in p
    assert OUTPUT_BLOCK in p


# ----------------------------------------------------------------------
# GPT Image 2 wrapper
# ----------------------------------------------------------------------


def test_gpt_image_2_has_change_preserve_constraints_triptych():
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "gpt_image_2",
    )
    assert "Change:" in p
    assert "Preserve:" in p
    assert "Constraints:" in p


def test_gpt_image_2_preserve_mentions_face_features():
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "gpt_image_2",
    )
    assert "face" in p.lower()
    assert "facial features" in p.lower()


def test_gpt_image_2_constraints_mentions_watermark_and_identity():
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "gpt_image_2",
    )
    assert "watermark" in p.lower()
    assert "identity" in p.lower()


# ----------------------------------------------------------------------
# Length budget
# ----------------------------------------------------------------------


@pytest.mark.parametrize("model", ["nano_banana_2", "gpt_image_2"])
@pytest.mark.parametrize("mode,style", [
    ("dating", "warm_outdoor"),
    ("dating", "urban_night"),
    ("cv", "corporate"),
    ("social", "influencer"),
])
def test_prompt_length_within_budget(model, mode, style):
    p = build_structured_prompt(mode, style, "male", None, model)
    assert len(p) <= settings.ab_prompt_max_len


# ----------------------------------------------------------------------
# Gender sensitivity
# ----------------------------------------------------------------------


def test_subject_block_reflects_gender():
    p_male = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "nano_banana_2",
    )
    p_female = build_structured_prompt(
        "dating", "warm_outdoor", "female", None, "nano_banana_2",
    )
    assert "man" in p_male.lower()
    assert "woman" in p_female.lower()


def test_unknown_gender_uses_neutral_phrasing():
    p = build_structured_prompt(
        "dating", "warm_outdoor", None, None, "nano_banana_2",
    )
    # "person in the reference photo" is the neutral fallback.
    assert "person" in p.lower()


# ----------------------------------------------------------------------
# Variant overrides
# ----------------------------------------------------------------------


def test_variant_scene_wins_over_spec_background():
    spec = STYLE_REGISTRY.get_or_default("dating", "warm_outdoor")
    if not getattr(spec, "variants", None):
        pytest.skip("spec has no variants")
    variant = spec.variants[0]
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", variant, "nano_banana_2",
    )
    # Either variant scene or spec background lands in the Scene block;
    # when variant has a scene it must be used.
    if variant.scene:
        assert variant.scene.split(",")[0].strip().rstrip(".") in p


# ----------------------------------------------------------------------
# Fallback path
# ----------------------------------------------------------------------


def test_unknown_mode_and_style_does_not_crash():
    p = build_structured_prompt(
        "mystery_mode", "alien_aesthetic", "male", None, "nano_banana_2",
    )
    assert "Subject:" in p
    assert CAMERA_BLOCK in p


def test_unknown_model_defaults_to_nano_banana_wrapper():
    # Falsy / unknown model keys fall through to the Nano Banana wrapper
    # so a misconfigured feature flag never silently emits a raw body.
    p = build_structured_prompt(
        "dating", "warm_outdoor", "male", None, "unknown_model",
    )
    assert "Change:" not in p
    assert NANO_BANANA_IDENTITY_ANCHOR in p
