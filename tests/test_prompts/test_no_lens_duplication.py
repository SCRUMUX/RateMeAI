"""v1.68 — lens-spec duplication guard.

The pre-v1.68 prompt pipeline mentioned the lens descriptor
``85mm short-telephoto lens at chest height`` in TWO places:

1. :data:`src.prompts.image_gen._COMPOSITION_NUMERICAL_HINT` (the
   cinematic composition anchor, emitted first).
2. :data:`src.prompts.image_gen.PHOTOREAL_BLOCK` (the photoreal
   camera/DoF block, emitted at the tail).

Two copies of the same lens token over-anchored a headshot
perspective on every framing — even full_body shots ended up with
a tighter perspective than the cinematic anchor's ``full-length
standing shot`` directive asked for. v1.68 keeps the lens spec
**only** in ``PHOTOREAL_BLOCK``; the cinematic anchor is now
lens-agnostic.

These tests pin that contract so a future maintainer can't silently
re-introduce the duplicate.
"""

from __future__ import annotations

import re

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _COMPOSITION_NUMERICAL_HINT,
    _DOCUMENT_STYLE_KEYS,
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


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_cinematic_anchor_does_not_carry_lens_token(framing: str):
    """The cinematic composition anchor must NOT contain a lens
    descriptor — that role belongs to ``PHOTOREAL_BLOCK``."""
    hint = _COMPOSITION_NUMERICAL_HINT[framing]
    assert "lens" not in hint, (
        f"framing={framing!r}: cinematic anchor re-introduced a "
        f"lens descriptor — v1.68 keeps the lens spec only in "
        f"PHOTOREAL_BLOCK to avoid the duplicate-mention over-anchor.\n"
        f"_COMPOSITION_NUMERICAL_HINT[{framing!r}]={hint!r}"
    )
    # Belt-and-braces: explicitly forbid common focal-length tokens.
    for token in ("85mm", "50mm", "35mm", "70mm"):
        assert token not in hint, (
            f"framing={framing!r}: cinematic anchor carries focal length "
            f"{token!r} — must live in PHOTOREAL_BLOCK only.\n"
            f"_COMPOSITION_NUMERICAL_HINT[{framing!r}]={hint!r}"
        )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_wire_prompt_mentions_85mm_exactly_once(framing: str):
    """In the final wire prompt the substring ``85mm`` must appear
    at most once across every non-document framing — that single
    mention lives in :data:`PHOTOREAL_BLOCK`.

    A count of 2+ means the duplicate has returned: the cinematic
    anchor is once again carrying its own lens token. Counter the
    audit and the production rollout immediately.
    """
    style = _pick_non_doc_dating_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    count_85mm = len(re.findall(r"\b85mm\b", prompt))
    assert count_85mm <= 1, (
        f"framing={framing!r}: ``85mm`` token appears {count_85mm} "
        f"times in the wire prompt — v1.68 dedupe expects exactly 1 "
        f"mention (the one in PHOTOREAL_BLOCK).\n{prompt!r}"
    )


def test_photoreal_block_keeps_lens_spec():
    """``PHOTOREAL_BLOCK`` is the new single source of truth for the
    lens descriptor. The token must still be present there — if a
    future edit drops it entirely, the dedup would be a regression
    (we'd lose the anti-selfie-perspective fix from v1.65)."""
    from src.prompts.image_gen import PHOTOREAL_BLOCK

    assert "85mm short-telephoto lens" in PHOTOREAL_BLOCK, (
        "PHOTOREAL_BLOCK must keep the 85mm short-telephoto lens "
        "anchor — it is the canonical fix for the selfie-perspective "
        "head-enlargement pathology."
    )
