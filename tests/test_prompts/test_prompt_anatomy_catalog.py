"""v1.70 catalog-wide anatomy invariants.

The v1.70 audit (``docs/ANATOMY_INVESTIGATION.md``) reversed the
direction of this test. Up to v1.69 the invariants asserted the
PRESENCE of head/lens/anchor tokens (``Reframe the reference into``,
``85mm short-telephoto lens``, etc.) because the doctrine was "more
anchors = better anatomy". The audit found the opposite: every added
anchor over v1.64..v1.69 increased the portrait-cue ratio in the wire
prompt without compensating gain, and the resulting prompt over-
anchored the model on tight head shots.

v1.70 removes those anchors entirely. The non-document wire prompt
must now be **free** of:

* ``head-and-shoulders``, ``bust shot``, ``upper third`` / ``upper
  fifth`` / ``upper quarter`` of the canvas — the
  ``_COMPOSITION_NUMERICAL_HINT`` cluster.
* ``head occupying`` / ``head-to-body`` / ``head-to-shoulders`` /
  ``head subtly turned`` — residual head-anchor wording.
* ``85mm`` / ``50-70mm`` / ``35-50mm`` lens descriptors — removed
  from ``PHOTOREAL_BLOCK`` in v1.70 (skin texture + light match
  only).
* ``shallow depth of field`` — removed with the lens.
* ``Anchor: the face occupies`` — face-area anchor removed.

Document styles (passport / visa / driver's licence) still legitimately
carry head-and-shoulders wording via ``DOC_PRESERVE``. They are
exempt from the cleanup and assert their own invariants below.

Identity preservation (``preserve the same person's facial features``,
``eye shape and colour``) MUST stay — identity is the only anchor we
never wanted to remove.

Length: the cleanup brings the typical non-document wire prompt
from ~1450 chars to ~600 chars. We pin a generous ``[300, 1100]``
band — values outside it indicate either a regression (anchor block
came back) or a catastrophic style-data shrink (scene_anchor went
empty).
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _DOCUMENT_STYLE_KEYS,
    _STUDIO_PORTRAIT_STYLE_KEYS,
    STYLE_REGISTRY,
)
from src.services.style_lint import forbidden_head_tokens_in_prompt
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


# v1.66 — portrait-pose tokens that must NOT leak into the wire prompt
# for non-studio styles. These are the semantic-conflict cluster that
# the v1.66 style-catalog normalization stripped from
# ``data/styles.json``; the test pins the catalog so the migration
# can't silently regress.
_V166_POSE_LEAK_TOKENS: tuple[str, ...] = (
    "authoritative steady",
    "leadership gaze",
    "distinguished gravitas",
    "executive vision",
    "timeless authority",
    "commanding charismatic",
    "leather chair",
    "behind a desk",
    "behind the desk",
    "webcam-friendly",
)


# v1.70 — lens descriptors that must NOT appear in non-document prompts.
_V170_LENS_LEAK_TOKENS: tuple[str, ...] = (
    "85mm short-telephoto",
    "85mm portrait lens",
    "50mm lens at eye level",
    "50-70mm normal-to-short-telephoto",
    "35-50mm normal-wide",
    "shallow depth of field",
)


_FRAMINGS: tuple[str, ...] = ("portrait", "half_body", "full_body")


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


def _photo_pairs() -> list[tuple[AnalysisMode, str]]:
    """All non-document (mode, style) pairs reachable via v3 registry."""
    mode_map = {
        "dating": AnalysisMode.DATING,
        "cv": AnalysisMode.CV,
        "social": AnalysisMode.SOCIAL,
    }
    pairs: list[tuple[AnalysisMode, str]] = []
    for (mode_str, key), _spec in STYLE_REGISTRY._v3_by_key.items():
        mode = mode_map.get(mode_str)
        if mode is None:
            continue
        if mode == AnalysisMode.CV and key in _DOCUMENT_STYLE_KEYS:
            continue
        pairs.append((mode, key))
    return pairs


def _doc_styles() -> list[str]:
    return sorted(
        key
        for key in _DOCUMENT_STYLE_KEYS
        if STYLE_REGISTRY.get_v3("cv", key) is not None
    )


@pytest.mark.parametrize(
    "mode,style", _photo_pairs(), ids=lambda v: str(v),
)
@pytest.mark.parametrize("framing", _FRAMINGS)
def test_v1_70_anatomy_invariants(mode: AnalysisMode, style: str, framing: str):
    """Catalog x framings — v1.70 anatomy contract MUST hold everywhere."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        mode, style=style, gender="male", framing=framing,
    )

    label = f"{mode.value}/{style}/framing={framing}"

    # v1.70 — head-cue defensive check. Reuses the public lint helper
    # so both this test and ``test_no_head_cues`` exercise the same
    # token list.
    head_leaks = forbidden_head_tokens_in_prompt(prompt, style_id=style)
    assert not head_leaks, (
        f"{label}: forbidden head-portrait tokens leaked into the wire "
        f"prompt: {head_leaks!r}. v1.70 removed all head-anchor clauses; "
        "re-introducing one is almost always a regression.\n"
        f"{prompt!r}"
    )

    for token in _V170_LENS_LEAK_TOKENS:
        assert token not in prompt, (
            f"{label}: lens/DoF descriptor {token!r} leaked back into "
            "the wire prompt — v1.70 removed lens + shallow DoF from "
            "PHOTOREAL_BLOCK; only ``natural skin texture`` and "
            "``lighting matches the scene`` survive.\n"
            f"{prompt!r}"
        )

    assert "Anchor: the face occupies" not in prompt, (
        f"{label}: face-area anchor leaked back in — "
        "_FACE_AREA_ANCHOR_BY_FRAMING is empty in v1.70.\n"
        f"{prompt!r}"
    )

    # Identity must still be there — it's the one anchor we never removed.
    assert "preserve the same person's facial features" in prompt, (
        f"{label}: IDENTITY_PRESERVE_BLOCK anchor missing (v1.67 wording)\n"
        f"{prompt!r}"
    )
    assert "eye shape and colour" in prompt, (
        f"{label}: identity textural anchor 'eye shape and colour' missing\n"
        f"{prompt!r}"
    )
    assert "identical face shape" not in prompt, (
        f"{label}: legacy 'identical face shape' anchor must not return — "
        "v1.67 dropped 'face shape' because edit-models read it as a "
        "geometric constraint that copied the reference head/torso ratio\n"
        f"{prompt!r}"
    )

    # v1.70 — skin texture survives.
    assert "Authentic skin texture" in prompt, (
        f"{label}: PHOTOREAL_BLOCK skin-texture anchor missing.\n"
        f"{prompt!r}"
    )

    if style not in _STUDIO_PORTRAIT_STYLE_KEYS:
        lower_prompt = prompt.lower()
        for token in _V166_POSE_LEAK_TOKENS:
            assert token not in lower_prompt, (
                f"{label}: v1.66 portrait-pose token {token!r} leaked "
                "into the wire prompt — the style-catalog "
                "normalization (migrate.py) must strip these from "
                "non-studio styles\n"
                f"{prompt!r}"
            )

    assert 300 <= len(prompt) <= 1100, (
        f"{label}: prompt length {len(prompt)} outside [300,1100] — "
        "either an anchor block came back (regression) or the style "
        "data collapsed (scene/wardrobe gone).\n"
        f"{prompt!r}"
    )


@pytest.mark.parametrize("style", _doc_styles())
def test_document_styles_keep_doc_anchors(style: str):
    """Document styles legitimately retain head-and-shoulders wording
    via ``DOC_PRESERVE`` / ``DOC_QUALITY``; they bypass the v1.70
    cleanup intentionally because passport / visa / driver's licence
    formats are vendor-specified tight headshots."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV, style=style, gender="male", framing="portrait",
    )

    assert "id-style headshot" in prompt.lower(), (
        f"cv/{style}: DOC_QUALITY identity anchor missing\n{prompt!r}"
    )

    # Lint helper auto-exempts document styles — sanity-check that path.
    assert forbidden_head_tokens_in_prompt(prompt, style_id=style) == [], (
        f"cv/{style}: lint helper failed to exempt document style — "
        "this would block legitimate visa/passport prompts.\n"
        f"{prompt!r}"
    )
