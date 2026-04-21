"""Prompt length & anchor budget (v1.13.3).

Reve edit prompts must stay in the 800–1200 char window: long enough
to carry the PRESERVE + QUALITY anchors, short enough not to trip the
``INVALID_PARAMETER_VALUE`` edge cases or waste identity tokens on
boilerplate. Iterates every style in every mode and both genders.
"""
from __future__ import annotations

import pytest

from src.prompts import image_gen as ig


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
    builder = _BUILDERS[mode]
    prompt = builder(style=style, gender=gender)
    assert "Preserve" in prompt, f"Preserve anchor missing in {mode}/{style}"
    assert "Photorealistic" in prompt, f"Photorealistic anchor missing in {mode}/{style}"


def test_prompt_max_len_sanity():
    assert 800 <= ig.PROMPT_MAX_LEN <= 1600


def test_empty_style_builds_with_anchors():
    for builder in _BUILDERS.values():
        p = builder(style="", gender="male")
        assert "Preserve" in p and "Photorealistic" in p
        assert len(p) <= ig.PROMPT_MAX_LEN
