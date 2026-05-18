"""v1.64 numerical composition anchor — production guarantees.

Background
----------

After the A/B cutover to GPT Image 2 Edit / Nano Banana 2 Edit, the
"identity_scene" path (PuLID, full-frame regeneration from a face crop)
stopped firing in production: ``UnifiedImageGenProvider._pick_backend``
prioritised the requested model over ``generation_mode``. Edit models,
fed a tight-selfie reference, copied the input's head/torso ratio
verbatim and produced "oversized head, pasted face" artefacts on
half_body / full_body framings — most visible on career studio styles
with a minimalist scene description.

Document styles never had this problem because their wrapper appends a
``Composition: ... face fills X% of frame ...`` sentence directly
(:data:`src.prompts.image_gen._DOC_COMPOSITION_HINT`). v1.64 mirrors
that mechanism for non-document styles via
:data:`src.prompts.image_gen._COMPOSITION_NUMERICAL_HINT`, injected by
``model_wrappers._assemble`` BEFORE :data:`IDENTITY_PRESERVE_BLOCK`.

These tests lock the contract:

* The numerical hint appears in the final prompt for every non-doc
  framing.
* It is positioned BEFORE the identity-preserve block (layout target
  wins attention over identity-copy).
* It does NOT appear when ``framing`` is left unset — the legacy
  no-framing path keeps its older behaviour for callers that do not
  thread a framing key through (defensive: avoids regressing the
  bot's "framing=None" default).
* Document styles still use their own ``_DOC_COMPOSITION_HINT`` —
  the new dict must not leak into the document wrapper branch.
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
    """Return the first registered v3 non-doc dating style.

    Concrete style choice doesn't matter — the numerical anchor is
    injected by the wrapper, which is style-agnostic. We just need a
    registered key so ``build_image_prompt_v2`` returns a non-None
    prompt.
    """
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        if mode_str == "dating" and key not in _DOCUMENT_STYLE_KEYS:
            return key
    raise RuntimeError("No non-doc dating styles registered")


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_numerical_anchor_present_in_prompt(framing: str):
    """Each known framing emits its ``Composition: ...`` sentence."""
    style = _pick_non_doc_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )

    expected_hint = _COMPOSITION_NUMERICAL_HINT[framing]
    assert expected_hint in prompt, (
        f"framing={framing!r} numerical anchor missing.\n"
        f"Expected fragment: {expected_hint!r}\n"
        f"Prompt: {prompt!r}"
    )
    assert f"Composition: {expected_hint}" in prompt, (
        f"framing={framing!r} numerical anchor lost its 'Composition: ' prefix"
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_numerical_anchor_precedes_identity_block(framing: str):
    """Layout target must win attention over identity-copy — that's
    the whole point of v1.64. If a future refactor flips the order,
    the model is back to "match the reference layout, then copy the
    face" and the oversized-head pathology returns.
    """
    style = _pick_non_doc_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male", framing=framing,
    )

    hint_pos = prompt.find(_COMPOSITION_NUMERICAL_HINT[framing])
    identity_pos = prompt.find("identical face shape, eye shape and colour")
    assert hint_pos >= 0
    assert identity_pos >= 0
    assert hint_pos < identity_pos, (
        f"framing={framing!r} numerical anchor at {hint_pos} must come "
        f"BEFORE identity block at {identity_pos}.\nPrompt: {prompt!r}"
    )


def test_no_numerical_anchor_when_framing_unset():
    """Calling ``build_image_prompt`` without ``framing`` (legacy bot
    default) keeps the older path: no numerical anchor injected.

    This is the regression guard — the bot relies on framing-less calls
    for some user flows; adding an unconditional anchor would change
    the wire prompt for every existing user.
    """
    style = _pick_non_doc_style()
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING, style=style, gender="male",
    )

    for fragment in _COMPOSITION_NUMERICAL_HINT.values():
        assert fragment not in prompt, (
            f"framing=None must skip numerical anchor, but found "
            f"{fragment!r} in prompt: {prompt!r}"
        )


def test_numerical_anchor_skipped_for_document_styles():
    """Document styles use their own ``_DOC_COMPOSITION_HINT`` —
    the wrapper's doc branch never references
    :data:`_COMPOSITION_NUMERICAL_HINT`.
    """
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

    portrait_hint = _COMPOSITION_NUMERICAL_HINT["portrait"]
    assert portrait_hint not in prompt, (
        "Document path must use _DOC_COMPOSITION_HINT, not the v1.64 "
        "non-doc numerical anchor.\nPrompt: " + repr(prompt)
    )


def test_identity_block_does_not_dictate_composition():
    """v1.64 trimmed the "head and shoulders read as real human
    proportions" tail from :data:`IDENTITY_PRESERVE_BLOCK`. If a
    future maintainer adds it back, this test fires loudly — the
    tail conflicts with non-portrait framings ("waist up", "full
    body") and was one of the root causes of the v1.63 oversized-
    head regression.
    """
    forbidden_tails = (
        "head and shoulders read",
        "real human proportions",
        "Body pose adapts naturally",
    )
    for fragment in forbidden_tails:
        assert fragment not in IDENTITY_PRESERVE_BLOCK, (
            f"IDENTITY_PRESERVE_BLOCK must not contain {fragment!r}; "
            "composition is the numerical anchor's job, identity is "
            "strictly about the face."
        )
