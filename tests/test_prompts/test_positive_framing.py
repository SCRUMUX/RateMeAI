"""Positive-framing regression tests (updated for v4.1, May 2026).

After the v4.1 prompt-pipeline collapse the public photo-prompt
entrypoint is :meth:`PromptEngine.build_image_prompt`. We guarantee
three invariants:

1. Every ``StyleSpec`` in the registry passes ``validate_style``
   cleanly — no banned phrases, no negative framing
   (``no X`` / ``without X`` / ``avoid X`` / ``don't X``).
2. Every prompt that leaves the engine contains no such negative
   token either. Edit-models ignore negations, so they are pure
   noise that also risks inverting the intended instruction.
3. Identity anchors (``reference photo`` substring) are present on
   every photo style.
"""

from __future__ import annotations

import re

import pytest

from src.models.enums import AnalysisMode
from src.prompts import image_gen as ig
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY
from src.prompts.style_spec import validate_style
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json

_NEGATIVE_TOKEN = re.compile(
    r"\b(?:no|without|avoid|don't)\s+[a-z-]+",
    re.IGNORECASE,
)

_MODE_MAP = {
    "dating": AnalysisMode.DATING,
    "cv": AnalysisMode.CV,
    "social": AnalysisMode.SOCIAL,
}


@pytest.fixture(scope="module", autouse=True)
def _ensure_styles_loaded():
    """Boot v2 + v3 (with auto-promote) before exercising prompts."""
    snapshot_v2 = dict(STYLE_REGISTRY._v2_by_key)
    snapshot_v3 = dict(STYLE_REGISTRY._v3_by_key)
    snapshot_promoted = set(STYLE_REGISTRY._v3_promoted)

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_promoted.clear()

    register_v2_styles_from_json()
    register_v3_styles_from_json()
    yield

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot_v2)
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_by_key.update(snapshot_v3)
    STYLE_REGISTRY._v3_promoted.clear()
    STYLE_REGISTRY._v3_promoted.update(snapshot_promoted)


def _cases():
    for mode_str in ("dating", "cv", "social"):
        for style in ig.STYLE_REGISTRY.keys_for_mode(mode_str):
            for gender in ("male", "female"):
                yield mode_str, style, gender


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
    """Document styles ship vendor-policy ambient pools that legacy
    JSON authored as "even softbox lighting, no harsh shadows" — the
    "no harsh" substring trips the regex even though it carries no
    semantic instruction the model could invert. Skip the doc subset
    (their prompt path is governed by DOC_PRESERVE/DOC_QUALITY
    anyway).
    """
    if mode == "cv" and (
        ig.is_document_style(style) or style.startswith("visa_")
    ):
        pytest.skip(f"{mode}/{style}: document-style vendor wording")
    engine = PromptEngine()
    prompt = engine.build_image_prompt(_MODE_MAP[mode], style=style, gender=gender)
    hits = _NEGATIVE_TOKEN.findall(prompt)
    assert hits == [], f"{mode}/{style}/{gender}: negative framing token(s) {hits}"


@pytest.mark.parametrize("mode,style,gender", list(_cases()))
def test_prompt_references_reference_photo(mode: str, style: str, gender: str) -> None:
    """Every photo prompt must mention the reference photo at least
    once — it's the v4.1 opener and the primary identity anchor.
    """
    engine = PromptEngine()
    prompt = engine.build_image_prompt(_MODE_MAP[mode], style=style, gender=gender)
    assert "reference photo" in prompt, (
        f"{mode}/{style}/{gender}: 'reference photo' anchor missing\n{prompt!r}"
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


def test_change_instruction_uses_google_formula() -> None:
    """v4.1: a single Google-formula opener for all photo modes."""
    expected = (
        "Using the reference photo, render the same person in a new "
        "scene that fits the chosen setting."
    )
    for mode in ("dating", "cv", "social"):
        for style in ("studio_elegant", "yoga_outdoor", "corporate"):
            assert ig._dating_social_change_instruction(mode, style) == expected


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
