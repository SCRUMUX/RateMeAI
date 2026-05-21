"""v4.1 / v1.67 single-path prompt anchors — production guarantees.

This is the tip of the prompt-pipeline test pyramid: it walks the
entire registered photo catalog, builds each style's final prompt
through the public :class:`PromptEngine` entrypoint, and asserts the
core invariants the model relies on:

* Identity anchors from :data:`IDENTITY_PRESERVE_BLOCK` are present
  ("preserve the same person's facial features: eye shape and colour"
  in v1.67). v1.67 dropped the "face shape" anchor because edit-models
  read it as a geometric constraint that copied the reference head /
  torso ratio (the "huge head" pathology). v1.64 dropped the legacy
  "head and shoulders read as real human proportions" tail because it
  conflicted with non-portrait framings; composition is now driven
  geometrically by ``reference_preprocess.pad_reference_for_framing``
  (v1.70 retired the textual ``_COMPOSITION_NUMERICAL_HINT`` anchor).
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

    # Opener (Google formula). v1.70 replaced the v1.65 head-anchor
    # tail (``Recompose the body so head, shoulders and torso read at
    # natural human proportions.``) with a head-free formulation that
    # asks for natural body proportions without giving the model a
    # geometric anchor for the head size.
    assert (
        "Using the reference photo, render the same person in a new "
        "scene that fits the chosen setting. Show the subject naturally "
        "with realistic body proportions."
        in prompt
    ), f"{mode.value}/{style}: opener missing\n{prompt!r}"
    assert "Recompose the body so head, shoulders and torso" not in prompt, (
        f"{mode.value}/{style}: v1.65 head-anchor opener returned — "
        "v1.70 removed the ``head, shoulders and torso`` clause.\n"
        f"{prompt!r}"
    )

    # Identity-preserve anchors (v1.67: "face shape" anchor removed —
    # edit-models read it as a geometric constraint on the head/torso
    # ratio. v1.64: "head and shoulders read as real human
    # proportions" tail removed — composition is now driven by
    # ``reference_preprocess.pad_reference_for_framing`` geometry).
    assert (
        "preserve the same person's facial features" in prompt
    ), f"{mode.value}/{style}: identity anchor missing\n{prompt!r}"
    assert (
        "eye shape and colour" in prompt
    ), f"{mode.value}/{style}: identity textural anchors missing\n{prompt!r}"
    assert "identical face shape" not in prompt, (
        f"{mode.value}/{style}: legacy v1.65 'identical face shape' "
        "anchor must not return — it pulled edit-models toward copying "
        "the reference head/torso ratio (the 'huge head' pathology).\n"
        f"{prompt!r}"
    )
    assert (
        "head and shoulders read as real human proportions" not in prompt
    ), (
        f"{mode.value}/{style}: v1.32 'head and shoulders read as real "
        "human proportions' tail must not return — it conflicts with "
        "non-portrait framings. Composition is now anchored "
        "geometrically by reference_preprocess.\n"
        f"{prompt!r}"
    )

    # v1.70 — lens / DoF descriptors removed from PHOTOREAL_BLOCK. The
    # block now carries only the skin-texture anchor and the
    # light-match instruction (see docs/ANATOMY_INVESTIGATION.md F3).
    assert "Authentic skin texture" in prompt, (
        f"{mode.value}/{style}: skin-texture anchor missing\n{prompt!r}"
    )
    assert "85mm short-telephoto lens" not in prompt, (
        f"{mode.value}/{style}: v1.69 ``85mm short-telephoto lens`` "
        "anchor must not return — v1.70 removed the entire lens spec "
        "from PHOTOREAL_BLOCK.\n"
        f"{prompt!r}"
    )
    assert "85mm portrait lens" not in prompt, (
        f"{mode.value}/{style}: legacy v1.65 ``85mm portrait lens`` "
        "must not return.\n"
        f"{prompt!r}"
    )
    assert "50mm lens at eye level" not in prompt, (
        f"{mode.value}/{style}: legacy 50mm anchor must not return.\n"
        f"{prompt!r}"
    )
    assert "shallow depth of field" not in prompt, (
        f"{mode.value}/{style}: v1.69 ``shallow depth of field`` anchor "
        "must not return — v1.70 removed lens + DoF together.\n"
        f"{prompt!r}"
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
