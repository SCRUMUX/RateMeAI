"""v1.68 P2.9 — LIGHT_MATCH_CLAUSE position in the wire prompt.

When ``settings.light_match_clause_enabled`` is True the wrapper
inserts :data:`LIGHT_MATCH_CLAUSE` immediately BEFORE
:data:`IDENTITY_PRESERVE_BLOCK` so it sits at the tail of the prompt
where edit-models weigh it heavily via recency bias. Identity still
gets the very last word — that keeps identity preservation strictly
above lighting realism when the two conflict.

These tests pin three contracts:

* Flag ON: the clause appears in the prompt for every framing.
* Flag ON: the clause appears BEFORE the identity-preserve block
  (the clause must end up at the prompt tail, not in the middle).
* Flag OFF: the clause never appears — the prompt is byte-for-byte
  unchanged from the v1.67 baseline.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    IDENTITY_PRESERVE_BLOCK,
    LIGHT_MATCH_CLAUSE,
    STYLE_REGISTRY,
)
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


@pytest.fixture(scope="module", autouse=True)
def _register_all_styles():
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


def _pick_non_doc_style() -> str:
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        if mode_str == "dating" and key not in _DOCUMENT_STYLE_KEYS:
            return key
    raise RuntimeError("No non-doc dating styles registered")


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_light_match_clause_present_when_flag_on(framing: str, monkeypatch):
    monkeypatch.setattr(settings, "light_match_clause_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    assert LIGHT_MATCH_CLAUSE in prompt, (
        f"framing={framing!r}: LIGHT_MATCH_CLAUSE missing despite flag on.\n"
        f"Prompt: {prompt!r}"
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_light_match_clause_precedes_identity_block(framing: str, monkeypatch):
    """Clause sits at the tail, but identity still gets the last word.
    A regression that flips the order (identity before clause) is the
    failure mode the v1.67 audit explicitly called out — identity
    preservation must stay LAST.
    """
    monkeypatch.setattr(settings, "light_match_clause_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    light_pos = prompt.find(LIGHT_MATCH_CLAUSE)
    identity_pos = prompt.find(IDENTITY_PRESERVE_BLOCK[:40])
    assert light_pos >= 0
    assert identity_pos >= 0
    assert light_pos < identity_pos, (
        f"framing={framing!r}: LIGHT_MATCH_CLAUSE at {light_pos} must "
        f"precede IDENTITY_PRESERVE_BLOCK at {identity_pos}."
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_light_match_clause_absent_when_flag_off(framing: str, monkeypatch):
    monkeypatch.setattr(settings, "light_match_clause_enabled", False)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    assert LIGHT_MATCH_CLAUSE not in prompt, (
        f"framing={framing!r}: LIGHT_MATCH_CLAUSE leaked despite "
        f"flag off.\nPrompt: {prompt!r}"
    )
