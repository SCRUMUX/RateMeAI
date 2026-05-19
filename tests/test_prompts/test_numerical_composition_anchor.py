"""v1.70 — numerical composition anchor removed.

Background
----------

The v1.64..v1.69 pipeline injected a cinematic head-anchor
(``Reframe the reference into a head-and-shoulders bust shot ...``)
into the wire prompt via :data:`_COMPOSITION_NUMERICAL_HINT`. The
v1.70 audit (``docs/ANATOMY_INVESTIGATION.md`` F1, F4) attributed the
"oversized head" pathology to that anchor and the four other
head-cues it stacked with. The cleanup replaces the dict with an
empty mapping so the ``model_wrappers._assemble`` branch falls
through and the head-cue never reaches the wire prompt.

The geometric half of the doctrine survives in
``reference_preprocess.pad_reference_for_framing`` — the canvas is
still padded so the face lands at the correct relative size for the
requested framing. The textual half is gone.

These tests pin the negative contract:

* ``_COMPOSITION_NUMERICAL_HINT`` is empty (``{}``).
* No wire prompt for any framing carries a ``Composition: Reframe …``
  sentence.
* Identity remains the last block — the tail-attention slot.
* Document styles continue to use their own ``_DOC_COMPOSITION_HINT``.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _COMPOSITION_NUMERICAL_HINT,
    _DOCUMENT_STYLE_KEYS,
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


def test_numerical_anchor_dict_is_empty():
    """v1.70 — the dict must be empty so ``_assemble`` skips the block."""
    assert _COMPOSITION_NUMERICAL_HINT == {}, (
        "v1.70 expected _COMPOSITION_NUMERICAL_HINT to be empty; "
        f"got {_COMPOSITION_NUMERICAL_HINT!r}. Any re-introduction is a "
        "regression — the head-anchor wording belongs in DOC_PRESERVE "
        "only (document styles)."
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_no_composition_reframe_sentence_in_wire_prompt(framing: str):
    """No framing produces a ``Composition: Reframe …`` sentence anymore."""
    style = _pick_non_doc_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )
    assert "Reframe the reference into" not in prompt, (
        f"framing={framing!r}: v1.69 ``Reframe the reference into`` "
        "directive returned to the wire prompt — the entire purpose of "
        "v1.70 is that this clause is gone.\nPrompt: " + repr(prompt)
    )
    assert "Composition: Reframe" not in prompt, (
        f"framing={framing!r}: ``Composition: Reframe`` sentence "
        "returned.\nPrompt: " + repr(prompt)
    )


def test_no_numerical_anchor_when_framing_unset():
    """Same negative contract for the legacy framing=None path."""
    style = _pick_non_doc_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male",
    )
    assert "Reframe the reference into" not in prompt, (
        "framing=None: ``Reframe the reference into`` directive "
        "leaked.\nPrompt: " + repr(prompt)
    )


def test_document_styles_skip_non_doc_anchor():
    """Document styles still use ``_DOC_COMPOSITION_HINT``. They must
    not pick up any v1.69-era cinematic anchor wording even if the
    dict ever gets repopulated."""
    doc_styles = [
        key for key in _DOCUMENT_STYLE_KEYS
        if STYLE_REGISTRY.get_v3("cv", key) is not None
    ]
    if not doc_styles:
        pytest.skip("No document styles registered")

    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV, style=doc_styles[0], gender="male", framing="portrait",
    )
    assert "Reframe the reference into" not in prompt
    # Document path still uses _DOC_COMPOSITION_HINT — sanity-check the
    # ``Composition:`` prefix is there (it's part of _assemble's doc
    # branch wording).
    assert "Composition:" in prompt, (
        f"cv/{doc_styles[0]}: document prompt lost its `Composition:` "
        f"prefix — _DOC_COMPOSITION_HINT may not be firing.\n"
        f"Prompt: {prompt!r}"
    )


def test_identity_block_does_not_dictate_composition():
    """Carry-over from v1.64: identity block must not re-acquire the
    head-and-shoulders proportions tail that was the original v1.63
    regression."""
    forbidden_tails = (
        "head and shoulders read",
        "real human proportions",
        "Body pose adapts naturally",
    )
    for fragment in forbidden_tails:
        assert fragment not in IDENTITY_PRESERVE_BLOCK, (
            f"IDENTITY_PRESERVE_BLOCK must not contain {fragment!r}; "
            "identity is strictly about the face."
        )
