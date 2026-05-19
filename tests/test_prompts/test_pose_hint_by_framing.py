"""v1.68 P2.10 — per-framing pose hint after wardrobe.

When ``settings.pose_hint_enabled`` is True the wrapper emits a
framing-specific ``Pose: ...`` directive immediately after the
wardrobe line. The hint anchors a relaxed natural posture so the
model does not default to symmetrical "hero stance" framing on
full_body or stiff "passport-mug" framing on tight portraits.

These tests pin three contracts:

* Flag ON: the prompt carries the framing-specific pose fragment.
* Flag ON: the pose line sits AFTER the wardrobe line — the slot
  designed for body-geometry cues.
* Flag OFF: NONE of the three pose strings appear — legacy wire
  prompt unchanged.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    _POSE_BY_FRAMING,
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
def test_pose_hint_present_when_flag_on(framing: str, monkeypatch):
    monkeypatch.setattr(settings, "pose_hint_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    expected = _POSE_BY_FRAMING[framing]
    assert expected in prompt, (
        f"framing={framing!r}: pose fragment {expected!r} missing.\n"
        f"Prompt: {prompt!r}"
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_pose_hint_positioned_after_wardrobe(framing: str, monkeypatch):
    """``Pose:`` must follow ``Wardrobe:`` — body geometry sits next
    to wardrobe in the prompt structure.
    """
    monkeypatch.setattr(settings, "pose_hint_enabled", True)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    wardrobe_pos = prompt.find("Wardrobe:")
    pose_pos = prompt.find("Pose:")
    assert wardrobe_pos >= 0
    assert pose_pos >= 0
    assert wardrobe_pos < pose_pos, (
        f"framing={framing!r}: Pose at {pose_pos} must come after "
        f"Wardrobe at {wardrobe_pos}."
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_pose_hint_absent_when_flag_off(framing: str, monkeypatch):
    """Flag OFF: NONE of the three pose strings leak."""
    monkeypatch.setattr(settings, "pose_hint_enabled", False)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    for fragment in _POSE_BY_FRAMING.values():
        assert fragment not in prompt, (
            f"framing={framing!r}: pose fragment leaked despite flag "
            f"off.\nFragment: {fragment!r}\nPrompt: {prompt!r}"
        )
