"""v1.65 catalog-wide anatomy invariants.

The "huge head, tiny shoulders" pathology is a per-prompt problem,
but the fix is a global one: every prompt produced by the catalog
MUST carry the v1.65 anatomy contract, regardless of which mode /
style the user picks. This test parametrises over the entire
registered v3 catalog × every framing the policy can route to,
and asserts the invariants below for each final prompt.

Invariants for non-document styles:

* ``Reframe the reference into`` is present — the cinematic-vocabulary
  layout directive that replaces v1.64's percentage targets.
* Either ``85mm short-telephoto lens`` (portrait + half_body) or
  ``35mm lens`` (full_body) is present — the physical lens spec is
  the canonical anti-selfie-perspective fix. v1.66 renamed the
  short-tele lens from ``85mm portrait lens`` to drop the duplicate
  ``portrait`` mention that was acting as a recency-bias headshot pull.
* The identity anchor ``identical face shape, eye shape and colour``
  is present.
* The legacy ``50mm lens at eye level`` anchor is absent.
* The legacy v1.65 ``85mm portrait lens`` descriptor is absent
  (renamed in v1.66).
* The v1.63 head-and-shoulders identity tail
  ``head and shoulders read as real human proportions`` is absent.
* The ``Framing: head-and-shoulders close-up`` token from the
  v1.64-era ``framing_line`` is absent — duplicate framing signal.
* v1.66 portrait-pose semantic leaks (``leadership gaze``,
  ``gravitas``, ``behind a desk``, ``leather chair``) are absent
  outside the studio-portrait whitelist.
* Length stays in ``[650, 1550]`` characters.

Document styles bypass ``_COMPOSITION_NUMERICAL_HINT`` and use
``_DOC_COMPOSITION_HINT`` instead. Their invariants:

* Identity is carried by ``DOC_QUALITY`` (``id-style headshot``).
* ``_COMPOSITION_NUMERICAL_HINT`` strings do NOT leak in.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    _COMPOSITION_NUMERICAL_HINT,
    _DOCUMENT_STYLE_KEYS,
    _STUDIO_PORTRAIT_STYLE_KEYS,
    STYLE_REGISTRY,
)
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
def test_v1_65_anatomy_invariants(mode: AnalysisMode, style: str, framing: str):
    """Catalog × framings — anatomy contract MUST hold everywhere."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        mode, style=style, gender="male", framing=framing,
    )

    label = f"{mode.value}/{style}/framing={framing}"

    assert "Reframe the reference into" in prompt, (
        f"{label}: cinematic Reframe operator missing — "
        "_COMPOSITION_NUMERICAL_HINT may have been overridden\n"
        f"{prompt!r}"
    )

    if framing in ("portrait", "half_body"):
        assert "85mm short-telephoto lens" in prompt, (
            f"{label}: 85mm short-telephoto lens anchor missing for "
            "portrait/half_body — required by v1.65 to suppress the "
            "selfie-perspective head enlargement (renamed in v1.66 "
            "from ``85mm portrait lens`` to drop the duplicate "
            "``portrait`` recency cue)\n"
            f"{prompt!r}"
        )
    else:
        assert "35mm lens" in prompt, (
            f"{label}: 35mm lens anchor missing for full_body — "
            "required by v1.65 to capture head-to-toe without "
            "perspective distortion\n"
            f"{prompt!r}"
        )

    assert "identical face shape, eye shape and colour" in prompt, (
        f"{label}: IDENTITY_PRESERVE_BLOCK anchor missing\n{prompt!r}"
    )

    assert "50mm lens at eye level" not in prompt, (
        f"{label}: legacy 50mm-at-eye-level anchor must be gone\n"
        f"{prompt!r}"
    )
    assert "85mm portrait lens" not in prompt, (
        f"{label}: legacy v1.65 ``85mm portrait lens`` descriptor "
        "must not return — v1.66 renamed it to ``85mm short-telephoto "
        "lens`` to remove the duplicate ``portrait`` mention\n"
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
    assert "head and shoulders read as real human proportions" not in prompt, (
        f"{label}: v1.63 head-and-shoulders identity tail must not "
        "return — it conflicts with non-portrait framings\n"
        f"{prompt!r}"
    )
    assert "Framing: head-and-shoulders close-up" not in prompt, (
        f"{label}: ``framing_line`` duplicate must not leak into the "
        "wire prompt — v1.65 dropped it\n"
        f"{prompt!r}"
    )

    assert 650 <= len(prompt) <= 1550, (
        f"{label}: prompt length {len(prompt)} outside [650,1550]\n"
        f"{prompt!r}"
    )


@pytest.mark.parametrize("style", _doc_styles())
def test_document_styles_skip_non_doc_numerical_hint(style: str):
    """Document styles use ``_DOC_COMPOSITION_HINT``, not the v1.65
    cinematic anchor. None of the cinematic strings should leak into
    a document prompt."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV, style=style, gender="male", framing="portrait",
    )

    for fragment in _COMPOSITION_NUMERICAL_HINT.values():
        assert fragment not in prompt, (
            f"cv/{style}: document prompt MUST NOT contain non-doc "
            f"composition hint {fragment!r}\n{prompt!r}"
        )

    assert "id-style headshot" in prompt.lower(), (
        f"cv/{style}: DOC_QUALITY identity anchor missing\n{prompt!r}"
    )
