"""v1.71 — ``PHOTOREAL_BLOCK`` stays lens-agnostic.

The v1.68 P2.8 per-framing block (``_PHOTOREAL_BY_FRAMING``) was
removed in v1.70 (audit: ``docs/ANATOMY_INVESTIGATION.md`` F3) and
the marker dict itself was dropped in v1.71. The wire prompt now
carries the skin-texture and light-match anchors only, never a lens
descriptor.

Contracts pinned here:

* ``PHOTOREAL_BLOCK`` contains the skin-texture anchor and the
  light-match instruction (the only two clauses that survived the
  v1.70 cleanup).
* ``PHOTOREAL_BLOCK`` does NOT contain ``85mm`` / ``50-70mm`` /
  ``35-50mm`` lens descriptors or ``shallow depth of field``.
* The wire prompt for every framing carries the skin-texture
  anchor and no lens descriptor.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    PHOTOREAL_BLOCK,
    STYLE_REGISTRY,
)
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


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


def _pick_non_doc_style() -> str:
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        if mode_str == "dating" and key not in _DOCUMENT_STYLE_KEYS:
            return key
    raise RuntimeError("No non-doc dating styles registered")


def test_photoreal_block_no_lens_or_dof():
    """``PHOTOREAL_BLOCK`` must not carry lens / DoF wording in v1.70."""
    forbidden = (
        "85mm",
        "50mm",
        "35mm",
        "50-70mm",
        "35-50mm",
        "short-telephoto",
        "normal-wide",
        "shallow depth of field",
        "deeper depth of field",
        "moderate depth of field",
    )
    for token in forbidden:
        assert token not in PHOTOREAL_BLOCK, (
            f"PHOTOREAL_BLOCK still contains {token!r} after v1.70 "
            "cleanup. Lens / DoF wording was removed because it "
            "over-anchored portrait perspective.\nBlock: "
            f"{PHOTOREAL_BLOCK!r}"
        )


def test_photoreal_block_carries_skin_and_light_anchors():
    """The two clauses that survived the v1.70 cleanup must be there."""
    assert "Authentic skin texture" in PHOTOREAL_BLOCK
    assert "lighting matches the scene" in PHOTOREAL_BLOCK


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_wire_prompt_has_skin_anchor_and_no_lens(framing: str):
    """Every framing must carry the skin-texture anchor and no lens token.

    Until v1.70.3 this was parametrized over the
    ``photoreal_by_framing_enabled`` flag. v1.70.4 retired the flag
    after it became a verified no-op; v1.71 retired the marker dict.
    """
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    assert "85mm" not in prompt, (
        f"framing={framing!r}: lens descriptor leaked.\n"
        f"Prompt: {prompt!r}"
    )
    assert "Authentic skin texture" in prompt, (
        f"framing={framing!r}: skin-texture anchor missing.\n"
        f"Prompt: {prompt!r}"
    )
