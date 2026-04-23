"""Identity-lock anchor invariants for PRESERVE_PHOTO / PRESERVE_PHOTO_FACE_ONLY.

v1.17 hardens the preserve-photo prompts to pin FLUX.2 Pro Edit on the
reference person's face (bone structure, eye shape and colour, nose,
mouth, jawline, hairline, hair colour). These tests guard against
silent weakening of those anchors in future edits — if someone removes
one of the must-have phrases, or lets the prompt drift off-budget, the
test suite flags it before the deploy.

Positive framing is enforced elsewhere (``test_positive_framing.py``).
Here we only care about presence of the identity-lock vocabulary and
the length budget.
"""
from __future__ import annotations

import pytest

from src.prompts.image_gen import (
    IDENTITY_LOCK_SUFFIX,
    PRESERVE_PHOTO,
    PRESERVE_PHOTO_FACE_ONLY,
)


REQUIRED_ANCHORS = (
    "identical",
    "facial features",
    "skin tone",
    "hair",
    "proportions",
)


@pytest.mark.parametrize("prompt", [PRESERVE_PHOTO, PRESERVE_PHOTO_FACE_ONLY])
def test_preserve_prompts_contain_identity_anchors(prompt: str) -> None:
    lowered = prompt.lower()
    missing = [w for w in REQUIRED_ANCHORS if w not in lowered]
    assert not missing, (
        f"preserve-photo prompt is missing identity anchors: {missing}\n"
        f"prompt={prompt!r}"
    )


@pytest.mark.parametrize("prompt", [PRESERVE_PHOTO, PRESERVE_PHOTO_FACE_ONLY])
def test_preserve_prompts_stay_under_length_budget(prompt: str) -> None:
    # Budget: keep each block comfortably below ~800 chars so the
    # full assembled prompt still fits FLUX.2's effective attention
    # window even after style/scene additions.
    assert 50 < len(prompt) <= 800, (
        f"preserve-photo prompt length {len(prompt)} outside budget"
    )


def test_identity_lock_suffix_is_short_and_echo_free() -> None:
    assert 20 <= len(IDENTITY_LOCK_SUFFIX) <= 120
    lowered = IDENTITY_LOCK_SUFFIX.lower()
    assert (
        "same individual" in lowered
        or "same person" in lowered
    ), IDENTITY_LOCK_SUFFIX
