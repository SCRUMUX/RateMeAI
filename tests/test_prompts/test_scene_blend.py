"""Scene-blend / pasted-on guard smoke tests.

History
-------
1.32.2 introduced ``SCENE_BLEND_PHOTO`` — a 530-character "ambient
occlusion / contact shadow / color grading match / atmospheric depth"
block aimed at suppressing the "композит / вклеенное лицо" failure
mode on edit models. In production it backfired: the "color grading
and white balance match the scene's overall tone" clause directly
contradicted ``PRESERVE_PHOTO_FACE_ONLY``'s "preserve … skin tone".
Edit models resolved the conflict by re-grading the face on warm or
neon scenes, which read as "вклеено" anyway.

v4 (May 2026 — prompt-pipeline-overhaul) retires the long anchor and
ships a much shorter ``PASTED_ON_GUARD`` ("…blends with the scene's
lighting and shadows naturally, looking present in the scene rather
than pasted on top of it.") combined with an upstream
``IDENTITY_PRESERVE_BLOCK`` hoisted to the top of the prompt. The
``SCENE_BLEND_PHOTO`` constant name is preserved but now points at
``PASTED_ON_GUARD`` so external imports continue to resolve.

These tests pin the v4 contract:

1. The anchor (``SCENE_BLEND_PHOTO`` / ``PASTED_ON_GUARD``) carries the
   "pasted on" failure-mode vocabulary explicitly.
2. The anchor is positive-framed (no "no X / without X / avoid X /
   don't X") so it passes the FLUX Kontext negative-phrase guard.
3. Per-model wrappers all surface ``PASTED_ON_GUARD`` AND the new
   ``IDENTITY_PRESERVE_BLOCK`` anchor (preserve-first ordering).
4. Document styles still bypass the photo tail entirely.
5. Prompt length stays well under the safety budget — the v4 layout
   is supposed to be SHORTER, not longer.
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


# v4 vocabulary the new pasted-on guard must surface in the final
# wrapped prompt. Two short tokens — both must reach the wire after
# ``compress_prompt`` and ``_truncate``.
REQUIRED_TERMS: tuple[str, ...] = (
    "pasted on",
    "blends with",
)


def _make_ir(*, is_document: bool = False) -> CompositionIR:
    """Minimal IR equivalent to a v3 sample on a normal photo style."""
    return CompositionIR(
        mode="dating",
        style_key="warm_outdoor",
        change_instruction="Place the person in the reference photo into a new scene.",
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


def test_scene_blend_anchor_carries_pasted_on_vocabulary():
    """The v4 anchor must contain the explicit "pasted on" failure-mode
    wording — that is the whole reason the constant exists.
    Drift in the anchor wording should be deliberate — this test
    forces the change to land here, where reviewers see it."""
    blob = ig.SCENE_BLEND_PHOTO.lower()
    assert "pasted on" in blob, (
        f"SCENE_BLEND_PHOTO must mention 'pasted on'; got {ig.SCENE_BLEND_PHOTO!r}"
    )
    assert "blends with" in blob or "blend with" in blob, (
        f"SCENE_BLEND_PHOTO must talk about light/shadow blending; "
        f"got {ig.SCENE_BLEND_PHOTO!r}"
    )


def test_scene_blend_anchor_is_positive_framed():
    """FLUX Kontext rejects negative phrasing. The anchor must use
    positive ("blends", "looking present") wording only."""
    forbidden = (" no ", " without ", " avoid ", " don't ", " not ")
    blob = " " + ig.SCENE_BLEND_PHOTO.lower() + " "
    for tok in forbidden:
        assert tok not in blob, (
            f"SCENE_BLEND_PHOTO contains forbidden negative phrasing {tok!r}"
        )


def test_pasted_on_guard_alias_matches_scene_blend():
    """``PASTED_ON_GUARD`` is the v4 canonical name; ``SCENE_BLEND_PHOTO``
    is kept as a back-compat alias. They must point at the same string."""
    assert ig.PASTED_ON_GUARD == ig.SCENE_BLEND_PHOTO


def test_identity_preserve_block_carries_required_anchors():
    """``IDENTITY_PRESERVE_BLOCK`` is hoisted to the top of every v4
    photo prompt and carries the canonical identity vocabulary the
    edit-models rely on."""
    blob = ig.IDENTITY_PRESERVE_BLOCK.lower()
    for token in ("facial features", "bone structure", "skin tone", "hair"):
        assert token in blob, (
            f"IDENTITY_PRESERVE_BLOCK missing token {token!r}; "
            f"got {ig.IDENTITY_PRESERVE_BLOCK!r}"
        )


# ---------- per-model wrappers all carry the v4 anchors -----------------


@pytest.mark.parametrize(
    "tail,name",
    [
        (QUALITY_PHOTO_GPT, "QUALITY_PHOTO_GPT"),
        (QUALITY_PHOTO_NANO, "QUALITY_PHOTO_NANO"),
        (QUALITY_PHOTO_FLUX, "QUALITY_PHOTO_FLUX"),
    ],
)
def test_per_model_tail_includes_pasted_on_guard(tail, name):
    assert ig.PASTED_ON_GUARD in tail, f"{name} missing PASTED_ON_GUARD"


@pytest.mark.parametrize(
    "wrapper",
    [wrap_for_gpt_image_2, wrap_for_nano_banana_2, wrap_for_flux_kontext],
)
def test_wrapper_emits_v4_anchors(wrapper):
    """Each per-model wrapper must surface BOTH the pasted-on guard
    vocabulary AND the identity-preserve block in the assembled
    prompt. Survives :func:`compress_prompt` / :func:`_truncate`."""
    prompt = wrapper(_make_ir())
    lower = prompt.lower()
    for term in REQUIRED_TERMS:
        assert term in lower, (
            f"{wrapper.__name__} dropped {term!r}; "
            f"prompt={prompt!r}"
        )
    # IDENTITY_PRESERVE_BLOCK is hoisted to position 2 (right after the
    # change_instruction opener); we assert presence — its specific
    # ordering is exercised by tests/test_prompts/test_v3_composition.py.
    assert "facial features" in lower
    assert "bone structure" in lower


# ---------- document paths skip the photo tail entirely -----------------


def test_document_path_does_not_emit_pasted_on_guard():
    """DOC styles use DOC_PRESERVE / DOC_QUALITY (vendor-policy
    identity tail) and bypass the per-model tail entirely.
    PASTED_ON_GUARD does not apply to ID-photo composition."""
    prompt = wrap_for_gpt_image_2(_make_ir(is_document=True))
    assert "pasted on" not in prompt.lower()
    assert "blends with" not in prompt.lower()


# ---------- prompt length stays under the safety budget -----------------


def test_v4_prompt_stays_under_safety_budget():
    """v4 trimmed the legacy ~1100-char tail (PRESERVE + QUALITY +
    LIGHT_INTEGRATION + SCENE_BLEND_PHOTO_LEGACY + CAMERA + ANATOMY +
    1:7 head-to-body addendum) down to ``PHOTOREAL_BLOCK + PASTED_ON_GUARD``
    plus a hoisted ``IDENTITY_PRESERVE_BLOCK`` — total ~530 chars of
    fixed tail per prompt. We assert the wrapped prompt stays well
    under 1600 chars on a typical IR (about 35% smaller than the v1.32
    baseline) — leaving headroom for long change_instruction strings
    and clothing pools."""
    prompt = wrap_for_gpt_image_2(_make_ir())
    assert len(prompt) < 1600, (
        f"Prompt exceeded v4 safety budget: {len(prompt)} chars\n{prompt!r}"
    )
    assert len(prompt) <= ig.PROMPT_MAX_LEN, "wrapper bypassed _truncate"
