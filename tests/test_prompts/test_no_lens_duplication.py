"""v1.70 — lens-spec absence guard.

The pre-v1.70 prompt pipeline carried a lens descriptor
(``85mm short-telephoto lens at chest height``) inside
``PHOTOREAL_BLOCK``. After the audit
(``docs/ANATOMY_INVESTIGATION.md`` F3) we concluded that the lens
token contributed to over-anchoring portrait perspective without
delivering a measurable benefit; v1.70 removed it.

The original ``test_no_lens_duplication`` test asserted at-most-one
mention of ``85mm`` per wire prompt. The v1.70 contract is
stronger: there must be ZERO lens descriptors in any non-document
wire prompt, and ``PHOTOREAL_BLOCK`` itself must not carry the token
either.
"""

from __future__ import annotations

import re

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


def _pick_non_doc_dating_style() -> str:
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        if mode_str == "dating" and key not in _DOCUMENT_STYLE_KEYS:
            return key
    raise RuntimeError("No non-doc dating styles registered")


def test_photoreal_block_has_no_lens_token():
    """``PHOTOREAL_BLOCK`` must not contain any focal-length descriptor."""
    for token in ("85mm", "50mm", "35mm", "70mm", "lens"):
        assert token not in PHOTOREAL_BLOCK, (
            f"PHOTOREAL_BLOCK still contains {token!r} — v1.70 removed "
            "the lens spec entirely.\nBlock: " + repr(PHOTOREAL_BLOCK)
        )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_wire_prompt_carries_no_lens_descriptor(framing: str):
    """Final wire prompt must not contain any focal-length token."""
    style = _pick_non_doc_dating_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    for token in (r"\b85mm\b", r"\b50mm\b", r"\b35mm\b", r"\b70mm\b"):
        matches = re.findall(token, prompt)
        assert not matches, (
            f"framing={framing!r}: lens token {token!r} found "
            f"{len(matches)} times in the wire prompt. v1.70 removed "
            "all lens descriptors from PHOTOREAL_BLOCK.\n"
            f"{prompt!r}"
        )
