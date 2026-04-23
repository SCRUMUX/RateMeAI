"""Prompt length & anchor budget (v1.13.3).

Reve edit prompts must stay in the 800–1200 char window: long enough
to carry the PRESERVE + QUALITY anchors, short enough not to trip the
``INVALID_PARAMETER_VALUE`` edge cases or waste identity tokens on
boilerplate. Iterates every style in every mode and both genders.
"""
from __future__ import annotations

import pytest

from src.prompts import image_gen as ig
from src.prompts.style_spec import detect_generation_mode


_BUILDERS = {
    "dating": ig.build_dating_prompt,
    "cv": ig.build_cv_prompt,
    "social": ig.build_social_prompt,
}

_STYLES_BY_MODE = {
    "dating": list(ig.DATING_STYLES.keys()),
    "cv": list(ig.CV_STYLES.keys()),
    "social": list(ig.SOCIAL_STYLES.keys()),
}


def _cases():
    for mode, styles in _STYLES_BY_MODE.items():
        for style in styles:
            for gender in ("male", "female"):
                yield mode, style, gender


@pytest.mark.parametrize("mode,style,gender", list(_cases()))
def test_prompt_under_1200_chars(mode: str, style: str, gender: str) -> None:
    builder = _BUILDERS[mode]
    prompt = builder(style=style, gender=gender)
    assert 0 < len(prompt) <= ig.PROMPT_MAX_LEN, (
        f"{mode}/{style}/{gender} prompt is {len(prompt)} chars"
    )


@pytest.mark.parametrize("mode,style,gender", list(_cases()))
def test_prompt_contains_preserve_and_photorealistic(mode: str, style: str, gender: str) -> None:
    # v1.18: the prompt template now branches on ``generation_mode``.
    # ``scene_preserve`` styles (documents, "keep my own photo") still
    # carry the full PRESERVE_PHOTO + QUALITY_PHOTO anchors. The
    # ``identity_scene`` branch (PuLID) intentionally drops the
    # Preserve-... clause because the ID adapter locks the face at the
    # model level — repeating "identical face" there harms Lightning's
    # scene reconstruction. The scene branch is validated instead by
    # the solo-subject anchor ("reference person" / "Single subject").
    builder = _BUILDERS[mode]
    prompt = builder(style=style, gender=gender)
    assert "Photorealistic" in prompt, f"Photorealistic anchor missing in {mode}/{style}"
    generation_mode = detect_generation_mode(style, mode)
    if generation_mode == "scene_preserve":
        assert "Preserve" in prompt, (
            f"Preserve anchor missing in scene_preserve {mode}/{style}"
        )
    else:
        # v1.19: opener says "reference subject" (not "reference
        # person") and SOLO_SUBJECT_ANCHOR moved to the negative_prompt.
            assert "reference photo" in prompt, (
                f"identity_scene opener missing in {mode}/{style}"
            )


def test_prompt_max_len_sanity():
    assert 800 <= ig.PROMPT_MAX_LEN <= 3000


def test_empty_style_builds_with_anchors():
    # Empty style falls back to an ``identity_scene`` default through the
    # get_or_default path, so we assert the identity_scene anchors rather
    # than the PRESERVE_PHOTO string that only applies to scene_preserve.
    for builder in _BUILDERS.values():
        p = builder(style="", gender="male")
        assert "Photorealistic" in p
        assert "reference photo" in p
        assert len(p) <= ig.PROMPT_MAX_LEN
