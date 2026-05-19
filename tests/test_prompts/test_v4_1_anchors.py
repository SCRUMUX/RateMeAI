"""v4.1 / v1.65 single-path prompt anchors — production guarantees.

This is the tip of the prompt-pipeline test pyramid: it walks the
entire registered photo catalog, builds each style's final prompt
through the public :class:`PromptEngine` entrypoint, and asserts the
core invariants the model relies on:

* Identity anchors from :data:`IDENTITY_PRESERVE_BLOCK` are present
  ("identical face shape, eye shape and colour"). v1.64 dropped the
  legacy "head and shoulders read as real human proportions" tail
  because it conflicted with non-portrait framings; composition is now
  driven exclusively by :data:`_COMPOSITION_NUMERICAL_HINT`.
* Photoreal anchors from :data:`PHOTOREAL_BLOCK` are present. v1.65
  swapped the camera anchor from ``50mm lens at eye level`` to
  ``85mm portrait lens`` to break the "selfie perspective" pattern
  that drove the "huge head" pathology.
* The v4.1 wardrobe label ``"Wardrobe:"`` replaces the legacy
  ``"Subject is wearing"`` phrasing.
* No leftover negative-framed tokens (``unchanged``, ``pasted``,
  ``rather than``) — the v4.0 wording violated Google / OpenAI
  best-practices and is gone.
* Prompt length stays in the 650-1550 char band — long enough to fit
  scene + wardrobe + identity + cinematic composition, short enough
  to leave attention budget for the user's reference image. v1.65
  bumped the upper bound by ~50 chars to fit the ``Reframe …`` /
  ``Recompose …`` cinematic clauses.

Document styles use the vendor-policy DOC_PRESERVE / DOC_QUALITY
layout so they bypass the v4.1 photo anchors. They get their own
narrow assertions.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    STYLE_REGISTRY,
)
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "unchanged",
    "pasted",
    "rather than",
    "Subject is wearing",
)


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


def _registered_photo_styles() -> list[tuple[AnalysisMode, str]]:
    """All (mode, style) pairs reachable via the v3 registry."""
    pairs: list[tuple[AnalysisMode, str]] = []
    mode_map = {
        "dating": AnalysisMode.DATING,
        "cv": AnalysisMode.CV,
        "social": AnalysisMode.SOCIAL,
    }
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        mode = mode_map.get(mode_str)
        if mode is None:
            continue
        pairs.append((mode, key))
    return pairs


def test_registry_is_non_empty():
    """The auto-promoter MUST register every photo style as v3."""
    pairs = _registered_photo_styles()
    assert len(pairs) > 50, (
        f"Expected >50 v3 specs, got {len(pairs)}. The v2→v3 "
        "auto-promoter likely failed."
    )


@pytest.mark.parametrize(
    "mode,style", _registered_photo_styles(), ids=lambda v: str(v),
)
def test_v4_1_anchors_present(mode: AnalysisMode, style: str):
    """Every registered photo style emits the v4.1 anchors."""
    if mode == AnalysisMode.CV and style in _DOCUMENT_STYLE_KEYS:
        # Document styles use the vendor-policy DOC layout — covered
        # by a separate assertion below.
        return

    engine = PromptEngine()
    prompt = engine.build_image_prompt(mode, style=style, gender="male")

    # Opener (Google formula). v1.65 appended a positive-framed
    # ``Recompose the body …`` clause so the opener also carries an
    # anatomy directive — the assertion below covers both halves.
    assert (
        "Using the reference photo, render the same person in a new "
        "scene that fits the chosen setting. Recompose the body so "
        "head, shoulders and torso read at natural human proportions."
        in prompt
    ), f"{mode.value}/{style}: opener missing\n{prompt!r}"

    # Identity-preserve anchors (v1.64: "head and shoulders read as
    # real human proportions" tail removed — composition is now driven
    # by ``_COMPOSITION_NUMERICAL_HINT`` only).
    assert (
        "identical face shape, eye shape and colour" in prompt
    ), f"{mode.value}/{style}: identity anchor missing\n{prompt!r}"
    assert (
        "head and shoulders read as real human proportions" not in prompt
    ), (
        f"{mode.value}/{style}: v1.32 'head and shoulders read as real "
        "human proportions' tail must not return — it conflicts with "
        "non-portrait framings. Use _COMPOSITION_NUMERICAL_HINT instead.\n"
        f"{prompt!r}"
    )

    # Photoreal anchors. v1.65 replaced the ``50mm lens at eye level``
    # selfie-perspective wording with ``85mm portrait lens at chest
    # height``. v1.66 then dropped the word ``portrait`` from the lens
    # descriptor (``85mm short-telephoto lens``) — keeping a second
    # ``portrait`` mention in the prompt acted as a recency-bias
    # headshot pull on edit models, fighting the cinematic
    # composition anchor that explicitly calls for a ``bust shot``.
    assert "85mm short-telephoto lens" in prompt, (
        f"{mode.value}/{style}: 85mm camera anchor missing\n{prompt!r}"
    )
    assert "85mm portrait lens" not in prompt, (
        f"{mode.value}/{style}: legacy v1.65 lens descriptor "
        "``85mm portrait lens`` must not return — v1.66 renamed it to "
        "``85mm short-telephoto lens`` to remove the recency-bias "
        "headshot pull from the second ``portrait`` mention.\n"
        f"{prompt!r}"
    )
    assert "50mm lens at eye level" not in prompt, (
        f"{mode.value}/{style}: legacy 50mm anchor must not return — "
        "it is the canonical 'selfie perspective' wording and "
        "reintroduces the huge-head pathology.\n"
        f"{prompt!r}"
    )
    assert "shallow depth of field" in prompt, (
        f"{mode.value}/{style}: DoF anchor missing\n{prompt!r}"
    )

    # Wardrobe label replaces legacy "Subject is wearing".
    assert "Wardrobe:" in prompt, (
        f"{mode.value}/{style}: wardrobe label missing\n{prompt!r}"
    )

    # No leftover negative-framed tokens from v4.0.
    for token in _FORBIDDEN_TOKENS:
        assert token not in prompt, (
            f"{mode.value}/{style}: forbidden token {token!r} present\n"
            f"{prompt!r}"
        )

    # Length budget: 650-1550 characters covers identity + scene +
    # wardrobe + photoreal block + cinematic composition without
    # bloating into the v1.32 ~1100+ tail. v1.64 trimmed the identity
    # tail (-60 chars) so the lower bound dropped to 650; v1.65 added
    # the cinematic Reframe / Recompose clauses (+~50 chars) so the
    # upper bound moved from 1500 to 1550.
    assert 650 <= len(prompt) <= 1550, (
        f"{mode.value}/{style}: prompt length {len(prompt)} outside "
        f"[650,1550]\n{prompt!r}"
    )


@pytest.mark.parametrize("style", sorted(_DOCUMENT_STYLE_KEYS))
def test_document_styles_use_doc_anchors(style: str):
    """Document CV styles bypass the photo anchors and use DOC_*
    blocks. Identity is still locked via DOC_PRESERVE.

    A few document keys (e.g. ``driver_license``) have no entry in
    ``data/styles.json`` yet — skip those rather than asserting a
    promoted spec exists.
    """
    if STYLE_REGISTRY.get_v3("cv", style) is None:
        pytest.skip(f"cv/{style}: not registered in styles.json")
    engine = PromptEngine()
    prompt = engine.build_image_prompt(AnalysisMode.CV, style=style, gender="male")

    # Doc-specific identity language.
    assert "id-style headshot" in prompt.lower(), (
        f"{style}: DOC_QUALITY missing\n{prompt!r}"
    )
    # Composition hint always present for documents.
    assert "Composition:" in prompt, (
        f"{style}: composition hint missing\n{prompt!r}"
    )
