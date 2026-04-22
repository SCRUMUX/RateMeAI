"""Prompt-layer fixes for the head-crop × full-body failure mode (v1.14.2).

Two orthogonal mitigations:

1. **PRESERVE_PHOTO vs PRESERVE_PHOTO_FACE_ONLY** — for styles flagged
   ``needs_full_body`` the base PRESERVE anchor previously said
   "keep original pose, framing and body proportions", which directly
   contradicts a prompt asking for a yoga / beach / running scene.
   Full-body styles now use ``PRESERVE_PHOTO_FACE_ONLY`` (no pose clamp)
   while classic close-up styles keep the full anchor.

2. **Close-up framing hint** — when the caller passes
   ``input_hints={"face_area_ratio": 0.4+}`` together with a full-body
   style, the prompt appends an explicit "keep portrait crop, do not
   invent a body" sentence, which steers Kontext Pro toward the only
   pose it can actually anchor to the pixels it was given.
"""
from __future__ import annotations

from src.prompts.image_gen import (
    PRESERVE_PHOTO,
    PRESERVE_PHOTO_FACE_ONLY,
    build_dating_prompt,
)


def test_full_body_style_uses_face_only_preserve():
    prompt = build_dating_prompt(style="yoga_outdoor", gender="male")
    # The prompt must not pin the reference pose for a scene that changes it.
    assert "original pose" not in prompt.lower()
    # But identity anchors from the face-only variant must still be there.
    assert "bone structure" in prompt.lower()


def test_close_up_style_keeps_full_preserve_anchor():
    prompt = build_dating_prompt(style="studio_elegant", gender="male")
    # studio_elegant is a close-up style, so we still want pose preservation.
    # The full PRESERVE_PHOTO anchor must appear somewhere in the prompt.
    # Use a distinctive fragment that only lives in PRESERVE_PHOTO.
    marker = "original pose and body proportions"
    assert marker in prompt, "expected full PRESERVE_PHOTO anchor for close-up style"


def test_close_up_hint_appears_for_tight_head_crop_with_full_body_style():
    """face_area_ratio=0.45 + yoga_outdoor → extra framing note."""
    prompt = build_dating_prompt(
        style="yoga_outdoor",
        gender="male",
        input_hints={"face_area_ratio": 0.45},
    )
    assert "close-up portrait" in prompt.lower()
    assert "do not extend the body" in prompt.lower()


def test_close_up_hint_absent_for_normal_face_ratio():
    """face_area_ratio=0.15 → no extra framing note even for full-body style."""
    prompt = build_dating_prompt(
        style="yoga_outdoor",
        gender="male",
        input_hints={"face_area_ratio": 0.15},
    )
    assert "do not extend the body" not in prompt.lower()


def test_close_up_hint_absent_for_portrait_style_even_with_tight_crop():
    """Close-up styles do not need the hint regardless of face ratio."""
    prompt = build_dating_prompt(
        style="studio_elegant",
        gender="male",
        input_hints={"face_area_ratio": 0.6},
    )
    assert "do not extend the body" not in prompt.lower()


def test_preserve_variants_are_distinct_strings():
    """Guard against accidental collapse of the two anchors back into one."""
    assert PRESERVE_PHOTO != PRESERVE_PHOTO_FACE_ONLY
    assert "original pose" in PRESERVE_PHOTO
    assert "original pose" not in PRESERVE_PHOTO_FACE_ONLY
