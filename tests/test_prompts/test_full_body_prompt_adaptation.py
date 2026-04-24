"""Prompt-layer fixes for the head-crop × full-body failure mode (v1.14.2+).

**v1.16** removed the "close-up framing note" branch from
``_build_mode_prompt`` — it was a Kontext Pro-era workaround that
forced a portrait crop for full-body styles when the reference was a
head-crop selfie, effectively turning "yoga" into "headshot wearing
yoga clothes". FLUX.2 Pro Edit at 2 MP consistently invents the lower
body from ``PRESERVE_PHOTO_FACE_ONLY`` + scene description alone, so
the contradiction is gone and the mitigation is no longer needed.

**v1.26.1** unified the identity anchor across every non-doc A/B style.
Previously ``needs_full_body`` styles used ``PRESERVE_PHOTO_FACE_ONLY``
(face-only clamp, pose adapts) and close-up styles used
``PRESERVE_PHOTO`` + a ``"Keep the original pose"`` sentence in the
change-instruction. That pose clamp directly contradicted the
user-selected ``framing`` from step 3 of the wizard (e.g. "portrait"
framing on a reference whose original pose was full-body would be
silently ignored because the prompt said "keep the original pose"
first). The clamp is now gone for every non-doc style; document styles
(passport / visa / photo_3x4) still get ``DOC_PRESERVE`` + a fixed
``Composition:`` line because ID photo regulations require it.

What we still guard:

1. **PRESERVE_PHOTO vs PRESERVE_PHOTO_FACE_ONLY** — the constants are
   still distinct strings so that the legacy non-A/B path (and any
   future caller) can pick either anchor. In the A/B path we always
   emit ``PRESERVE_PHOTO_FACE_ONLY`` — see the unified branch in
   ``_build_mode_prompt``.
2. ``input_hints`` is accepted without crashing and does **not**
   introduce the old framing-note sentence for any face ratio.
"""

from __future__ import annotations

from src.prompts.image_gen import (
    PRESERVE_PHOTO,
    PRESERVE_PHOTO_FACE_ONLY,
    build_dating_prompt,
)


def test_full_body_style_uses_face_only_preserve():
    prompt = build_dating_prompt(style="yoga_outdoor", gender="male")
    assert "original pose" not in prompt.lower()
    assert "adopting a natural pose that fits the scene" in prompt
    assert "Photorealistic" in prompt


def test_close_up_style_drops_pose_clamp():
    """v1.26.1: close-up стили тоже без pose-clamp — лицо фиксируется
    через PRESERVE_PHOTO_FACE_ONLY, поза/кадр определяются сценой и
    пользовательским framing из шага 3."""
    prompt = build_dating_prompt(style="studio_elegant", gender="male")
    assert "original pose" not in prompt.lower()
    assert "original framing" not in prompt.lower()
    assert "Body pose naturally fits the new scene" in prompt
    assert "Photorealistic" in prompt


def test_no_framing_note_for_any_face_ratio_on_full_body_style():
    """v1.16 removed the contradictory framing note entirely."""
    for ratio in (0.05, 0.25, 0.45, 0.7):
        prompt = build_dating_prompt(
            style="yoga_outdoor",
            gender="male",
            input_hints={"face_area_ratio": ratio},
        )
        assert "do not extend the body" not in prompt.lower()
        assert "framing note" not in prompt.lower()


def test_input_hints_accepted_for_close_up_style():
    prompt = build_dating_prompt(
        style="studio_elegant",
        gender="male",
        input_hints={"face_area_ratio": 0.6},
    )
    assert prompt, "builder must produce a non-empty prompt with hints"
    assert "do not extend the body" not in prompt.lower()


def test_preserve_variants_are_distinct_strings():
    """Guard against accidental collapse of the two anchors back into one.

    v1.25: the identity-anchor strings were consolidated into a single
    positive-framed block each; "original pose" moved out of
    PRESERVE_PHOTO and into the change_instruction (see
    ``_dating_social_change_instruction``). The distinguishing feature
    is now "Body pose naturally fits the new scene." in the face-only
    variant, and "natural pores" (a close-up-only detail) in the
    default variant.

    v1.26.1: A/B-путь всегда эмитит PRESERVE_PHOTO_FACE_ONLY, но
    обе константы сохраняются отдельно — их используют legacy
    non-A/B билдеры, и мы не хотим «сливать» два разных анкера в один.
    """
    assert PRESERVE_PHOTO != PRESERVE_PHOTO_FACE_ONLY
    assert "Body pose naturally fits the new scene" in PRESERVE_PHOTO_FACE_ONLY
    assert "Body pose naturally fits the new scene" not in PRESERVE_PHOTO
    assert "natural pores" in PRESERVE_PHOTO
    assert "natural pores" not in PRESERVE_PHOTO_FACE_ONLY
