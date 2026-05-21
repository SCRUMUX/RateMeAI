"""v1.70 — no-head-cues catalog sweep.

Lightweight smoke test that walks every registered v3 style, builds a
wire prompt for each of the three framings, and asserts that the
output is free of the v1.65-v1.69 head-anchor vocabulary. Document
styles are exempt (vendor format requires a head-and-shoulders crop).

The check is implemented in :func:`src.services.style_lint.
forbidden_head_tokens_in_prompt` and runs the SAME token list that the
catalog lint rule ``NO_HEAD_TOKEN_IN_PROMPT`` uses — so admin edits to
``data/styles.json`` and code edits to the prompt builders can't go
out of sync.

Companion fixtures: ``tests/fixtures/golden_prompts/*.txt``. The
golden-prompt sweep already proves byte-stability of the wire prompt;
this test proves that the wire prompt has the right *shape* (no head
tokens) for any style at any framing — even ones not in the goldens.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    STYLE_REGISTRY,
)
from src.services.style_lint import forbidden_head_tokens_in_prompt
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


_FRAMINGS: tuple[str, ...] = ("portrait", "half_body", "full_body")


@pytest.fixture(scope="module", autouse=True)
def _register_all_styles():
    snapshot_v2 = dict(STYLE_REGISTRY._v2_by_key)
    snapshot_v3 = dict(STYLE_REGISTRY._v3_by_key)

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()

    register_v2_styles_from_json()
    register_v3_styles_from_json()
    yield

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot_v2)
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_by_key.update(snapshot_v3)


def _photo_pairs() -> list[tuple[AnalysisMode, str]]:
    mode_map = {
        "dating": AnalysisMode.DATING,
        "cv": AnalysisMode.CV,
        "social": AnalysisMode.SOCIAL,
    }
    pairs: list[tuple[AnalysisMode, str]] = []
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        mode = mode_map.get(mode_str)
        if mode is None:
            continue
        if mode == AnalysisMode.CV and key in _DOCUMENT_STYLE_KEYS:
            continue
        pairs.append((mode, key))
    return pairs


@pytest.mark.parametrize(
    "mode,style", _photo_pairs(), ids=lambda v: str(v),
)
@pytest.mark.parametrize("framing", _FRAMINGS)
def test_no_head_cues_in_non_document_prompts(
    mode: AnalysisMode, style: str, framing: str
):
    """v1.70 — every non-document wire prompt is free of head-anchor cues."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        mode, style=style, gender="male", framing=framing,
    )
    leaks = forbidden_head_tokens_in_prompt(prompt, style_id=style)
    assert not leaks, (
        f"{mode.value}/{style}/framing={framing}: head-anchor tokens "
        f"leaked into the wire prompt: {leaks!r}.\n{prompt!r}"
    )


@pytest.mark.parametrize("style", sorted(_DOCUMENT_STYLE_KEYS))
def test_document_styles_are_exempt(style: str):
    """Document styles legitimately carry head-and-shoulders wording;
    the lint helper must not flag them."""
    if STYLE_REGISTRY.get_v3("cv", style) is None:
        pytest.skip(f"document style {style!r} not registered")
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV, style=style, gender="male", framing="portrait",
    )
    assert forbidden_head_tokens_in_prompt(prompt, style_id=style) == [], (
        f"cv/{style}: lint helper failed to exempt the document style.\n"
        f"{prompt!r}"
    )
