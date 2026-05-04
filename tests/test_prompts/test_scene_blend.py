"""Scene-blend anchor smoke tests (1.32.2).

These tests pin the contract of the new ``SCENE_BLEND_PHOTO`` anchor
in :mod:`src.prompts.image_gen` and the per-model wrapper plumbing
in :mod:`src.prompts.model_wrappers`:

1. The compositing-quality terms ("edge light wrap", "ambient
   occlusion", "contact shadow", "color grading", "atmospheric
   depth") survive the prompt-compression pipeline and reach the
   final wrapped prompt.
2. Both GPT Image 2 and Nano Banana 2 wrappers embed the anchor
   (per-model tails are no longer identical, but they all carry
   SCENE_BLEND_PHOTO).
3. FLUX Kontext wrapper is also wired up.
4. Document styles do NOT carry the scene-blend anchor — DOC paths
   bypass the tail entirely (DOC_PRESERVE / DOC_QUALITY only).

We deliberately stay above the model-evaluation layer — the user
will A/B-test the actual "embedded subject" quality on real
generations. These are smoke tests for the prompt content, not
quality assertions.
"""

from __future__ import annotations

import pytest

from src.prompts import image_gen as ig
from src.prompts.composition_builder import CompositionIR
from src.prompts.model_wrappers import (
    QUALITY_PHOTO_FLUX,
    QUALITY_PHOTO_GPT,
    QUALITY_PHOTO_NANO,
    wrap_for_flux_kontext,
    wrap_for_gpt_image_2,
    wrap_for_nano_banana_2,
)


REQUIRED_TERMS: tuple[str, ...] = (
    "edge light",
    "ambient occlusion",
    "contact shadow",
    "color grading",
    "atmospheric depth",
)


def _make_ir(*, is_document: bool = False) -> CompositionIR:
    """Minimal IR equivalent to a v3 sample on a normal photo style."""
    return CompositionIR(
        mode="dating",
        style_key="warm_outdoor",
        change_instruction="Change the background of the reference photo.",
        scene="warm urban street, soft golden lighting",
        lighting="soft golden",
        weather="clear",
        clothing="smart casual outfit",
        expression="confident relaxed expression",
        framing_line="",
        quality_identity_base="",
        per_model_tail_map={},
        is_document=is_document,
        framing_requested=False,
    )


# ---------- anchor content ----------------------------------------------


def test_scene_blend_anchor_includes_compositing_terms():
    """The constant itself must carry the five film-industry tokens.
    Drift in the anchor wording should be deliberate — this test
    forces the change to land here, where reviewers see it."""
    blob = ig.SCENE_BLEND_PHOTO.lower()
    for term in REQUIRED_TERMS:
        assert term in blob, f"SCENE_BLEND_PHOTO missing term: {term!r}"


def test_scene_blend_anchor_is_positive_framed():
    """FLUX Kontext rejects negative phrasing. The anchor must use
    positive ("ground", "match") wording only."""
    forbidden = (" no ", " without ", " avoid ", " don't ", " not ")
    blob = " " + ig.SCENE_BLEND_PHOTO.lower() + " "
    for tok in forbidden:
        assert tok not in blob, (
            f"SCENE_BLEND_PHOTO contains forbidden negative phrasing {tok!r}"
        )


# ---------- per-model wrappers all carry SCENE_BLEND --------------------


@pytest.mark.parametrize(
    "tail,name",
    [
        (QUALITY_PHOTO_GPT, "QUALITY_PHOTO_GPT"),
        (QUALITY_PHOTO_NANO, "QUALITY_PHOTO_NANO"),
        (QUALITY_PHOTO_FLUX, "QUALITY_PHOTO_FLUX"),
    ],
)
def test_per_model_tail_includes_scene_blend(tail, name):
    assert ig.SCENE_BLEND_PHOTO in tail, f"{name} missing SCENE_BLEND_PHOTO"


@pytest.mark.parametrize(
    "wrapper",
    [wrap_for_gpt_image_2, wrap_for_nano_banana_2, wrap_for_flux_kontext],
)
def test_wrapper_emits_scene_blend_terms(wrapper):
    """Each per-model wrapper assembles a prompt that retains the
    five compositing terms after :func:`compress_prompt` /
    :func:`_truncate`."""
    prompt = wrapper(_make_ir())
    lower = prompt.lower()
    for term in REQUIRED_TERMS:
        assert term in lower, (
            f"{wrapper.__name__} dropped {term!r}; "
            f"prompt={prompt!r}"
        )


# ---------- document paths skip the scene-blend anchor ------------------


def test_document_path_does_not_emit_scene_blend():
    """DOC styles use DOC_PRESERVE / DOC_QUALITY (vendor-policy
    identity tail) and bypass the per-model tail entirely.
    SCENE_BLEND would not survive the compression pipeline anyway,
    but we guard the absence to prevent a silent regression."""
    prompt = wrap_for_gpt_image_2(_make_ir(is_document=True))
    assert "ambient occlusion" not in prompt.lower()
    assert "contact shadow" not in prompt.lower()
    assert "edge light" not in prompt.lower()


# ---------- prompt length stays under the safety budget -----------------


def test_scene_blend_does_not_blow_prompt_budget():
    """Plan note: «новые scene-blend термины могут пересушить
    промпт (>500 токенов)». PROMPT_MAX_LEN in image_gen is 2500
    chars (≈600 tokens); SCENE_BLEND_PHOTO adds ~580 chars on
    top of LIGHT_INTEGRATION. We assert the total stays under
    2000 chars (≈480 tokens) on a typical IR so there's headroom
    for long change_instruction strings and clothing pools."""
    prompt = wrap_for_gpt_image_2(_make_ir())
    assert len(prompt) < 2000, (
        f"Prompt exceeded safety budget: {len(prompt)} chars\n{prompt!r}"
    )
    assert len(prompt) <= ig.PROMPT_MAX_LEN, "wrapper bypassed _truncate"
