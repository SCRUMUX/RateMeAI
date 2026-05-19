"""v1.68 P1.4 — percentage face-area anchor in the early-attention slot.

The cinematic ``_COMPOSITION_NUMERICAL_HINT`` owns the qualitative
composition slot (``bust shot`` / ``waist-up`` / ``full-length
standing``). The percentage-based ``_FACE_AREA_ANCHOR_BY_FRAMING``
gives the model an additional, quantitative cue at the prompt's head,
where edit models pay the most attention.

These tests pin three contracts:

* When ``settings.numerical_percent_anchor_enabled`` is True, the
  anchor for the resolved framing appears in the wire prompt.
* The anchor appears at the VERY HEAD of the prompt (before the
  cinematic composition hint and before the identity-preserve
  block) — that is the whole point of the early-attention slot.
* When the flag is False (legacy / rollback path) the anchor never
  fires — none of the three per-framing strings leak into the prompt.

The flag is toggled per-test through :func:`pytest.MonkeyPatch.setattr`
on the ``settings`` singleton so a single test run can cover both
states without restarting the interpreter or polluting other tests.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _COMPOSITION_NUMERICAL_HINT,
    _DOCUMENT_STYLE_KEYS,
    _FACE_AREA_ANCHOR_BY_FRAMING,
    IDENTITY_PRESERVE_BLOCK,
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
def test_anchor_present_when_flag_on(framing: str, monkeypatch):
    """Flag ON: the per-framing anchor string appears in the prompt."""
    monkeypatch.setattr(settings, "numerical_percent_anchor_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    expected = _FACE_AREA_ANCHOR_BY_FRAMING[framing]
    assert expected in prompt, (
        f"framing={framing!r}: percent anchor {expected!r} missing.\n"
        f"Prompt: {prompt!r}"
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_anchor_is_first_in_prompt(framing: str, monkeypatch):
    """Flag ON: the anchor must precede both the cinematic composition
    line and the identity-preserve block — that ordering is the whole
    reason for the anchor (early-attention slot).
    """
    monkeypatch.setattr(settings, "numerical_percent_anchor_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    anchor_pos = prompt.find(_FACE_AREA_ANCHOR_BY_FRAMING[framing])
    hint_pos = prompt.find(_COMPOSITION_NUMERICAL_HINT[framing])
    identity_pos = prompt.find(IDENTITY_PRESERVE_BLOCK[:40])
    assert anchor_pos >= 0
    assert hint_pos >= 0
    assert identity_pos >= 0
    assert anchor_pos < hint_pos, (
        f"framing={framing!r}: percent anchor at {anchor_pos} must precede "
        f"the cinematic hint at {hint_pos}."
    )
    assert anchor_pos < identity_pos, (
        f"framing={framing!r}: percent anchor at {anchor_pos} must precede "
        f"the identity block at {identity_pos}."
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_anchor_absent_when_flag_off(framing: str, monkeypatch):
    """Flag OFF: NONE of the three per-framing anchor strings leak."""
    monkeypatch.setattr(settings, "numerical_percent_anchor_enabled", False)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    for fragment in _FACE_AREA_ANCHOR_BY_FRAMING.values():
        assert fragment not in prompt, (
            f"framing={framing!r}: anchor {fragment!r} leaked despite "
            f"feature flag being disabled.\nPrompt: {prompt!r}"
        )
