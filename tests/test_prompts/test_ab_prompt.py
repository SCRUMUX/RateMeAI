"""Structural invariants for the v1.21 A/B prompt adapter (v1.23 form).

v1.23: the Nano Banana 2 wrapper now emits a concise 3-paragraph
prose prompt (identity anchor / change description / change-vs-preserve
split) instead of the 8-block stack — NB2 is a Gemini reasoning model
whose sweet spot per the fal.ai / Google prompting guides is 1-3
sentences per idea. The GPT Image 2 wrapper keeps the full 8-block
body plus the Change/Preserve/Constraints triptych because the
OpenAI prompting guide explicitly recommends structured + anchors.

We do NOT pin exact wording; instead we test the invariants that the
downstream models rely on:

- Nano Banana wrapper hard-locks the face via ``NANO_BANANA_IDENTITY_ANCHOR``
- Nano Banana wrapper pins natural skin texture (anti-"plastic" clause)
- GPT Image 2 wrapper contains the ``Change:/Preserve:/Constraints:``
  triptych with the extended identity inventory
- prompt length never exceeds ``settings.ab_prompt_max_len``
- gender is reflected in the Subject phrasing
- unknown modes / styles do not crash (fallback path)
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.prompts.ab_prompt import (
    CAMERA_BLOCK,
    GPT_CONSTRAINTS,
    GPT_PRESERVE_BASE,
    NANO_BANANA_IDENTITY_ANCHOR,
    NANO_BANANA_SKIN_CLAUSE,
    build_structured_prompt,
)
from src.prompts.image_gen import STYLE_REGISTRY


# ----------------------------------------------------------------------
# Nano Banana wrapper (v1.23 concise prose form)
# ----------------------------------------------------------------------


def test_nano_banana_prompt_is_concise_prose_no_stacked_block_labels():
    p = build_structured_prompt(
        mode="dating",
        style="warm_outdoor",
        gender="male",
        variant=None,
        model="nano_banana_2",
    )
    # v1.23: NB2 must NOT emit the stacked 8-block layout (every block
    # on its own line with a label), which is the format Gemini 3.1
    # Flash Image deprioritises. Inline ``Style: ...`` / ``Camera: ...``
    # tags inside the prose paragraph are fine per the Google Gemini
    # portrait-prompting guide — what we reject is the *structural*
    # labels that dominate the adapter output.
    for stacked_label in (
        "Subject:",
        "Scene:",
        "Identity & Realism:",
        "Enhancement:",
        "Output:",
    ):
        assert stacked_label not in p, (
            f"v1.23 NB2 prompt must not contain stacked label "
            f"{stacked_label!r}; prompt was:\n{p}"
        )
    # The prompt must split into exactly three prose paragraphs
    # (identity anchor / change / preserve).
    paragraphs = [p.strip() for p in p.split("\n\n") if p.strip()]
    assert len(paragraphs) == 3, f"expected 3 paragraphs, got {len(paragraphs)}:\n{p}"


def test_nano_banana_has_identity_anchor_first():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "nano_banana_2",
    )
    assert NANO_BANANA_IDENTITY_ANCHOR in p
    # Anchor must appear in the FIRST paragraph so the model sees it
    # before the scene description.
    first_paragraph = p.split("\n\n", 1)[0]
    assert NANO_BANANA_IDENTITY_ANCHOR in first_paragraph


def test_nano_banana_contains_do_not_alter_phrase():
    # Direct anchor from the Google Gemini portrait-preservation guide.
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "nano_banana_2",
    )
    assert "Do not alter the person's face" in p


def test_nano_banana_contains_natural_skin_texture_clause():
    # Anti-plastic/waxy-skin clause.
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "nano_banana_2",
    )
    assert NANO_BANANA_SKIN_CLAUSE in p


def test_nano_banana_has_camera_anchor_in_body():
    # The camera anchor still lands in the prose details paragraph.
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "nano_banana_2",
    )
    assert CAMERA_BLOCK in p


def test_nano_banana_has_explicit_change_preserve_split():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "nano_banana_2",
    )
    lowered = p.lower()
    assert "change only" in lowered
    assert "preserve" in lowered
    assert "face" in lowered
    assert "pose" in lowered


# ----------------------------------------------------------------------
# GPT Image 2 wrapper
# ----------------------------------------------------------------------


def test_gpt_image_2_has_change_preserve_constraints_triptych():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "gpt_image_2",
    )
    assert "Change:" in p
    assert "Preserve:" in p
    assert "Constraints:" in p


def test_gpt_image_2_preserve_mentions_face_features():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "gpt_image_2",
    )
    assert "face" in p.lower()
    assert "facial features" in p.lower()


def test_gpt_image_2_constraints_mentions_watermark_and_identity():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "gpt_image_2",
    )
    assert "watermark" in p.lower()
    assert "identity" in p.lower()


def test_gpt_image_2_preserve_uses_extended_inventory():
    # v1.23: preserve list must include explicit anchors (eye shape,
    # nose bridge, jawline, hairline) from the OpenAI fidelity guide.
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "gpt_image_2",
    )
    lowered = p.lower()
    for anchor in (
        "eye shape",
        "nose bridge",
        "jawline",
        "hairline",
        "skin texture",
        "expression",
        "framing",
    ):
        assert anchor in lowered, f"missing anchor {anchor!r}"
    # Constants themselves should appear verbatim.
    assert GPT_PRESERVE_BASE in p
    assert GPT_CONSTRAINTS in p


def test_gpt_image_2_constraints_ban_plastic_skin_and_airbrushing():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "gpt_image_2",
    )
    lowered = p.lower()
    assert "no plastic skin" in lowered
    assert "no airbrushing" in lowered
    assert "no face change" in lowered


# ----------------------------------------------------------------------
# Length budget
# ----------------------------------------------------------------------


@pytest.mark.parametrize("model", ["nano_banana_2", "gpt_image_2"])
@pytest.mark.parametrize(
    "mode,style",
    [
        ("dating", "warm_outdoor"),
        ("dating", "urban_night"),
        ("cv", "corporate"),
        ("social", "influencer"),
    ],
)
def test_prompt_length_within_budget(model, mode, style):
    p = build_structured_prompt(mode, style, "male", None, model)
    assert len(p) <= settings.ab_prompt_max_len


# ----------------------------------------------------------------------
# Gender sensitivity
# ----------------------------------------------------------------------


def test_subject_block_reflects_gender():
    p_male = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "nano_banana_2",
    )
    p_female = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "female",
        None,
        "nano_banana_2",
    )
    assert "man" in p_male.lower()
    assert "woman" in p_female.lower()


def test_unknown_gender_uses_neutral_phrasing():
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        None,
        None,
        "nano_banana_2",
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
    # v1.23: GPT-2 wrapper is the one that still carries labelled
    # blocks + explicit Scene; NB2 flattens to prose so we assert on
    # GPT-2 here.
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        variant,
        "gpt_image_2",
    )
    # Either variant scene or spec background lands in the Scene block;
    # when variant has a scene it must be used.
    if variant.scene:
        assert variant.scene.split(",")[0].strip().rstrip(".") in p


# ----------------------------------------------------------------------
# Fallback path
# ----------------------------------------------------------------------


def test_unknown_mode_and_style_does_not_crash():
    # v1.23 NB2 wrapper is prose — assert on the identity anchor and
    # camera anchor that must be present regardless of StyleSpec.
    p = build_structured_prompt(
        "mystery_mode",
        "alien_aesthetic",
        "male",
        None,
        "nano_banana_2",
    )
    assert NANO_BANANA_IDENTITY_ANCHOR in p
    assert CAMERA_BLOCK in p
    # GPT-2 wrapper keeps the labelled blocks — assert on that branch
    # too so the fallback path covers both models.
    p_gpt = build_structured_prompt(
        "mystery_mode",
        "alien_aesthetic",
        "male",
        None,
        "gpt_image_2",
    )
    assert "Subject:" in p_gpt
    assert CAMERA_BLOCK in p_gpt


def test_unknown_model_defaults_to_nano_banana_wrapper():
    # Falsy / unknown model keys fall through to the Nano Banana wrapper
    # so a misconfigured feature flag never silently emits a raw body.
    p = build_structured_prompt(
        "dating",
        "warm_outdoor",
        "male",
        None,
        "unknown_model",
    )
    assert "Change:" not in p
    assert NANO_BANANA_IDENTITY_ANCHOR in p
