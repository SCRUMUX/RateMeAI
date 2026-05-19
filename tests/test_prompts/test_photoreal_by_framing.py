"""v1.68 P2.8 — per-framing photoreal block (focal length by framing).

The legacy ``PHOTOREAL_BLOCK`` pinned every framing to 85mm + shallow
DoF. That combination is correct for ``portrait`` only — ``half_body``
reads better at 50-70mm + moderate DoF and ``full_body`` at 35-50mm
+ deeper DoF (the scene context must stay sharp behind the subject).

These tests pin three contracts:

* When ``settings.photoreal_by_framing_enabled`` is True, the
  prompt's photoreal tail contains the FRAMING-SPECIFIC focal
  length (85 / 50-70 / 35-50).
* When the flag is False the legacy single-block tail fires for
  every framing — the wire prompt is byte-for-byte unchanged from
  the v1.67 baseline.
* The legacy ``PHOTOREAL_BLOCK`` and the new
  ``_PHOTOREAL_BY_FRAMING["portrait"]`` carry the SAME focal length
  ("85mm"), so portrait users see no behavioural change when the
  flag flips — only half_body / full_body shift.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    _PHOTOREAL_BY_FRAMING,
    PHOTOREAL_BLOCK,
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


_EXPECTED_LENSES: dict[str, str] = {
    "portrait": "85mm short-telephoto",
    "half_body": "50-70mm",
    "full_body": "35-50mm",
}


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_photoreal_block_uses_framing_specific_lens_when_flag_on(
    framing: str, monkeypatch
):
    monkeypatch.setattr(settings, "photoreal_by_framing_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    expected_lens = _EXPECTED_LENSES[framing]
    assert expected_lens in prompt, (
        f"framing={framing!r}: expected lens fragment {expected_lens!r} "
        f"missing.\nPrompt: {prompt!r}"
    )


def test_half_body_prompt_does_not_carry_portrait_only_lens(monkeypatch):
    """Negative guard: half_body must NOT carry ``85mm`` once the
    framing-specific block fires — that was the whole point of the
    refactor. ``portrait`` keeps 85mm because the new portrait entry
    is identical to the legacy block.
    """
    monkeypatch.setattr(settings, "photoreal_by_framing_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing="half_body",
    )
    assert "85mm" not in prompt, (
        "half_body framing must use the 50-70mm block; "
        f"85mm leaked.\nPrompt: {prompt!r}"
    )


def test_legacy_block_used_when_flag_off(monkeypatch):
    """Flag OFF: every framing uses ``PHOTOREAL_BLOCK`` verbatim."""
    monkeypatch.setattr(settings, "photoreal_by_framing_enabled", False)
    style = _pick_non_doc_style()
    for framing in ("portrait", "half_body", "full_body"):
        prompt = PromptEngine().build_image_prompt(
            AnalysisMode.DATING, style=style, gender="male", framing=framing,
        )
        assert "85mm" in prompt, (
            f"framing={framing!r} with flag OFF must use legacy "
            f"PHOTOREAL_BLOCK (85mm).\nPrompt: {prompt!r}"
        )


def test_portrait_entry_is_lens_consistent_with_legacy_block():
    """The new portrait entry must carry 85mm so portrait users see
    no behavioural change when the flag flips.
    """
    assert "85mm short-telephoto" in _PHOTOREAL_BY_FRAMING["portrait"]
    assert "85mm short-telephoto" in PHOTOREAL_BLOCK
