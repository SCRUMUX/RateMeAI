"""Prompt-layer fixes for the head-crop × full-body failure mode (v1.14.2+).

**v1.16** removed the "close-up framing note" branch from
``_build_mode_prompt`` — it was a Kontext Pro-era workaround that
forced a portrait crop for full-body styles when the reference was a
head-crop selfie, effectively turning "yoga" into "headshot wearing
yoga clothes". FLUX.2 Pro Edit at 2 MP consistently invents the lower
body from ``PRESERVE_PHOTO_FACE_ONLY`` + scene description alone, so
the contradiction is gone and the mitigation is no longer needed.

What we still guard:

1. **PRESERVE_PHOTO vs PRESERVE_PHOTO_FACE_ONLY** — for styles flagged
   ``needs_full_body`` the base PRESERVE anchor previously said
   "keep original pose", which directly contradicts a yoga / beach /
   running scene. Full-body styles use ``PRESERVE_PHOTO_FACE_ONLY``
   (no pose clamp), classic close-up styles keep the full anchor.
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
    # v1.18: ``yoga_outdoor`` is an identity_scene style (PuLID). The
    # legacy PRESERVE_PHOTO_FACE_ONLY anchor does not ship in that
    # branch — identity is held by the ID adapter. We instead assert
    # that the scene opener is the full-body opener (so PuLID gets a
    # pose hint) and that there is no ``original pose`` clamp that
    # would contradict a yoga scene.
    prompt = build_dating_prompt(style="yoga_outdoor", gender="male")
    assert "original pose" not in prompt.lower()
    # v1.19: opener says "reference subject" (not "reference person")
    # to avoid duplicate-person tokens that were triggering two-subject
    # outputs. SOLO_SUBJECT_ANCHOR moved to PuLID negative_prompt.
    assert "full-body portrait of the reference subject" in prompt
    assert "Photorealistic" in prompt


def test_close_up_style_keeps_full_preserve_anchor():
    # v1.18: ``studio_elegant`` is also an identity_scene style, so the
    # full PRESERVE_PHOTO "original pose and body proportions" anchor
    # is intentionally absent. The non-full-body opener ships without
    # the pose hint — assert that we picked the close-up opener rather
    # than the full-body one, and that the Photorealistic + solo-subject
    # anchors are present.
    prompt = build_dating_prompt(style="studio_elegant", gender="male")
    assert "original pose" not in prompt.lower()
    # v1.19: opener rephrased from "reference person" to "reference
    # subject" — one mention of the subject avoids the two-person
    # failure mode under low CFG.
    assert "portrait of the reference subject in the scene" in prompt
    assert "full-body portrait" not in prompt
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
    """Guard against accidental collapse of the two anchors back into one."""
    assert PRESERVE_PHOTO != PRESERVE_PHOTO_FACE_ONLY
    assert "original pose" in PRESERVE_PHOTO
    assert "original pose" not in PRESERVE_PHOTO_FACE_ONLY
