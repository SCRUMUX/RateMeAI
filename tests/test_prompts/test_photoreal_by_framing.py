"""v1.70 — PHOTOREAL_BLOCK now lens-agnostic.

The v1.68 P2.8 per-framing block was removed in v1.70 (audit:
``docs/ANATOMY_INVESTIGATION.md`` F3). The block no longer carries
focal length or DoF; ``_PHOTOREAL_BY_FRAMING`` is retained for
import-compatibility but every entry points at the single
``PHOTOREAL_BLOCK`` so ``photoreal_by_framing_enabled`` is a no-op.

Contracts pinned here:

* ``PHOTOREAL_BLOCK`` contains the skin-texture anchor and the
  light-match instruction (the only two clauses that survived the
  v1.70 cleanup).
* ``PHOTOREAL_BLOCK`` does NOT contain ``85mm`` / ``50-70mm`` /
  ``35-50mm`` lens descriptors or ``shallow depth of field``.
* Every entry of ``_PHOTOREAL_BY_FRAMING`` is identical to
  ``PHOTOREAL_BLOCK`` — the per-framing dict is now a stub.
* The flag ``photoreal_by_framing_enabled`` is effectively a no-op:
  ON and OFF produce the same wire prompt for every framing.
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


def test_per_framing_dict_is_no_op():
    """Every entry of ``_PHOTOREAL_BY_FRAMING`` equals ``PHOTOREAL_BLOCK``
    after v1.70 (the per-framing lens map was collapsed)."""
    for framing in ("portrait", "half_body", "full_body"):
        assert _PHOTOREAL_BY_FRAMING[framing] == PHOTOREAL_BLOCK, (
            f"_PHOTOREAL_BY_FRAMING[{framing!r}] diverged from the "
            "single PHOTOREAL_BLOCK. v1.70 collapsed the dict — any "
            "divergence is a regression.\nGot: "
            f"{_PHOTOREAL_BY_FRAMING[framing]!r}\n"
            f"Expected: {PHOTOREAL_BLOCK!r}"
        )


@pytest.mark.parametrize("flag", [True, False])
@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_flag_is_no_op_on_wire_prompt(flag: bool, framing: str, monkeypatch):
    """``photoreal_by_framing_enabled`` produces the same prompt either way."""
    monkeypatch.setattr(settings, "photoreal_by_framing_enabled", flag)
    style = _pick_non_doc_style()
    prompt = PromptEngine().build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    assert "85mm" not in prompt, (
        f"flag={flag} framing={framing!r}: lens descriptor leaked.\n"
        f"Prompt: {prompt!r}"
    )
    assert "Authentic skin texture" in prompt, (
        f"flag={flag} framing={framing!r}: skin-texture anchor missing.\n"
        f"Prompt: {prompt!r}"
    )
