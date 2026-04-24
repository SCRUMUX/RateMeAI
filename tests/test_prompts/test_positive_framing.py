"""Positive-framing regression tests (v1.14.3).

After the Kontext-aligned prompt refresh we guarantee three invariants:

1. Every ``StyleSpec`` in the registry passes ``validate_style`` cleanly —
   no banned phrases, no negative framing (``no X`` / ``without X`` /
   ``avoid X`` / ``don't X``).
2. Every prompt that leaves ``build_*`` contains no such negative token
   either. FLUX.1 Kontext Pro ignores negations, so they are pure noise
   that also risks inverting the intended instruction.
3. Every prompt carries the two identity anchors we rely on for stable
   generation across scenes: ``skin tone`` and ``head-to-`` (matches
   ``head-to-shoulders`` or ``head-to-body``).
"""

from __future__ import annotations

import re

import pytest

from src.prompts import image_gen as ig
from src.prompts.style_spec import detect_generation_mode, validate_style

_NEGATIVE_TOKEN = re.compile(
    r"\b(?:no|without|avoid|don't)\s+[a-z-]+",
    re.IGNORECASE,
)

_BUILDERS = {
    "dating": ig.build_dating_prompt,
    "cv": ig.build_cv_prompt,
    "social": ig.build_social_prompt,
}


def _cases():
    for mode in _BUILDERS:
        for style in ig.STYLE_REGISTRY.keys_for_mode(mode):
            for gender in ("male", "female"):
                yield mode, style, gender


@pytest.mark.parametrize(
    "spec",
    list(
        ig.STYLE_REGISTRY.all_for_mode("dating")
        + ig.STYLE_REGISTRY.all_for_mode("cv")
        + ig.STYLE_REGISTRY.all_for_mode("social")
    ),
)
def test_validate_style_clean(spec) -> None:
    warnings = validate_style(spec)
    assert warnings == [], f"{spec.mode}/{spec.key}: {warnings}"


@pytest.mark.parametrize("mode,style,gender", list(_cases()))
def test_prompt_has_no_negative_framing(mode: str, style: str, gender: str) -> None:
    builder = _BUILDERS[mode]
    prompt = builder(style=style, gender=gender)
    hits = _NEGATIVE_TOKEN.findall(prompt)
    assert hits == [], f"{mode}/{style}/{gender}: negative framing token(s) {hits}"


@pytest.mark.parametrize("mode,style,gender", list(_cases()))
def test_prompt_contains_identity_anchors(mode: str, style: str, gender: str) -> None:
    # v1.18: identity anchors are only asserted on the edit-based
    # ``scene_preserve`` branch (Seedream / legacy FLUX). In the
    # ``identity_scene`` branch (PuLID) the ID adapter enforces identity
    # at the model level, and we deliberately drop the "skin tone" /
    # "head-to-body" clauses from the prompt because Lightning
    # over-commits to those tokens. The identity_scene opener carries
    # its own anchor ("reference person"), which is asserted instead.
    builder = _BUILDERS[mode]
    prompt = builder(style=style, gender=gender)
    generation_mode = detect_generation_mode(style, mode)
    if generation_mode == "scene_preserve":
        assert "skin tone" in prompt, f"{mode}/{style}/{gender}: missing 'skin tone'"
        assert "head-to-" in prompt, (
            f"{mode}/{style}/{gender}: missing 'head-to-*' proportion anchor"
        )
    else:
        # v1.19: identity_scene opener now says "reference subject"
        # (not "reference person") to avoid duplicate-"person" tokens
        # that were triggering two-subject outputs under low CFG.
        # The SOLO_SUBJECT_ANCHOR was moved out of the POSITIVE prompt
        # and into PuLID's negative_prompt, so it no longer appears
        # here — the PuLID API body carries it instead.
        assert "reference photo" in prompt, (
            f"{mode}/{style}/{gender}: identity_scene opener missing"
        )


def test_emoji_prompt_has_identity_power_words() -> None:
    prompt = ig.build_emoji_prompt(gender="male")
    assert "cartoon-styled version of the same person" in prompt.lower()
    assert "exact facial proportions" in prompt
    assert "skin tone" in prompt


def test_emoji_prompt_has_no_negative_framing() -> None:
    prompt = ig.build_emoji_prompt(gender="female", base_description="friendly")
    hits = _NEGATIVE_TOKEN.findall(prompt)
    assert hits == [], f"emoji prompt negatives: {hits}"


def test_change_instruction_focuses_on_composition() -> None:
    """v1.25: identity vocabulary was moved out of the change line
    into ``PRESERVE_PHOTO(_FACE_ONLY)`` to stop tripling the same
    signal across three anchors. The change_instruction now carries
    only the compositional delta (what to change + what to keep of
    the framing), and the identity anchors (skin tone, head-to-body)
    are asserted on the full prompt in
    ``test_prompt_contains_identity_anchors``.
    """
    # Non-full-body style — should speak of background + clothing only.
    dating = ig._dating_social_change_instruction("dating", "studio_elegant")
    assert "reference photo" in dating
    assert "background" in dating
    assert "clothing" in dating
    # Identity-scene / full-body — should phrase the scene placement.
    dating_full = ig._dating_social_change_instruction("dating", "yoga_outdoor")
    assert "reference photo" in dating_full
    assert "natural pose" in dating_full


def test_allowed_negatives_is_empty() -> None:
    from src.prompts.style_spec import _ALLOWED_NEGATIVES

    assert _ALLOWED_NEGATIVES == frozenset()


def test_negative_detector_catches_without_and_avoid() -> None:
    from src.prompts.style_spec import _has_disallowed_negative

    assert _has_disallowed_negative("clean backdrop without shadows")
    assert _has_disallowed_negative("avoid gradient")
    assert _has_disallowed_negative("don't show accessories")
    assert _has_disallowed_negative("no patterns")
    assert not _has_disallowed_negative("smooth matte finish")
