"""v1.71.2 — wardrobe filter + crop directive integration tests.

The May 2026 ``singapore_marina_bay`` post-mortem found that the
wire prompt carried zero crop signal on a portrait-class upload —
edit models given a padded portrait canvas, a wardrobe enumerating
``trousers`` / ``shoes`` and a sweeping outdoor scene comfortably
fabricated a full body on tight framing requests.

v1.71.2 closes the hole with two changes:

* :func:`src.prompts.image_gen.filter_wardrobe_by_framing` strips
  lower-body / footwear wardrobe segments on portrait / half_body
  framings (full_body passthrough). The catalogue keeps the full
  outfit for curatorial correctness; the runtime decides what
  reaches the wire prompt.
* :data:`src.prompts.image_gen._FRAMING_PROMPT_DIRECTIVES` is now
  emitted into the wire prompt right after wardrobe with explicit
  "Crop the frame above the chest; do not render the lower body."
  wording (v1.70-anatomy-lint compliant — no ``head-and-shoulders``
  / ``bust shot`` / ``upper third`` head-anchor tokens).

These tests pin both behaviours so future refactors can't silently
drop them.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import (
    STYLE_REGISTRY,
    _FRAMING_PROMPT_DIRECTIVES,
    filter_wardrobe_by_framing,
)
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


# ---------------------------------------------------------------------------
# filter_wardrobe_by_framing — unit-level
# ---------------------------------------------------------------------------


def test_filter_portrait_drops_lower_body_and_footwear():
    raw = (
        "smart fitted shirt, tailored dark trousers, polished modern shoes, "
        "well-fitted across the shoulders"
    )
    out = filter_wardrobe_by_framing(raw, "portrait")
    assert "trousers" not in out
    assert "shoes" not in out
    assert "well-fitted across the shoulders" in out
    assert "smart fitted shirt" in out


def test_filter_half_body_keeps_trousers_but_drops_footwear():
    raw = "smart fitted shirt, tailored dark trousers, polished modern shoes"
    out = filter_wardrobe_by_framing(raw, "half_body")
    assert "trousers" in out
    assert "shoes" not in out


def test_filter_full_body_is_passthrough():
    raw = "smart fitted shirt, tailored dark trousers, polished modern shoes"
    assert filter_wardrobe_by_framing(raw, "full_body") == raw


def test_filter_unknown_framing_is_passthrough():
    raw = "smart fitted shirt, tailored dark trousers, polished modern shoes"
    assert filter_wardrobe_by_framing(raw, None) == raw
    assert filter_wardrobe_by_framing(raw, "square") == raw


def test_filter_handles_footwear_synonyms():
    cases = (
        "blazer, loafers",
        "blazer, sneakers",
        "blazer, boots",
        "blazer, heels",
    )
    for raw in cases:
        out = filter_wardrobe_by_framing(raw, "portrait")
        assert out == "blazer", raw


def test_filter_keeps_neutral_top_only_when_everything_else_is_low():
    raw = "tailored dark trousers, polished modern shoes"
    assert filter_wardrobe_by_framing(raw, "portrait") == ""


def test_filter_preserves_commas_between_kept_segments():
    raw = "shirt, well-fitted, trousers, shoes, sharp grooming"
    out = filter_wardrobe_by_framing(raw, "portrait")
    assert out == "shirt, well-fitted, sharp grooming"


# ---------------------------------------------------------------------------
# Crop directive end-to-end
# ---------------------------------------------------------------------------


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


@pytest.mark.parametrize(
    "framing,expected_phrase",
    [
        ("portrait", _FRAMING_PROMPT_DIRECTIVES["portrait"]),
        ("half_body", _FRAMING_PROMPT_DIRECTIVES["half_body"]),
        ("full_body", _FRAMING_PROMPT_DIRECTIVES["full_body"]),
    ],
)
def test_crop_directive_present_in_wire_prompt(framing: str, expected_phrase: str):
    """Every non-document prompt for a known framing must carry the
    matching crop directive verbatim."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING,
        style="singapore_marina_bay",
        gender="male",
        framing=framing,
    )
    assert expected_phrase in prompt, (
        f"crop directive missing for framing={framing!r}\n{prompt!r}"
    )


def test_singapore_portrait_strips_trousers_and_shoes_in_wire_prompt():
    """Regression test for the May 2026 ``singapore_marina_bay`` failure
    — on a portrait framing the wire prompt MUST NOT enumerate any
    lower-body garments / footwear, even though the on-disk catalogue
    still does."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING,
        style="singapore_marina_bay",
        gender="male",
        framing="portrait",
    )
    lower = prompt.lower()
    for tok in (
        "trousers",
        "shoes",
        "loafers",
        "sneakers",
        "boots",
    ):
        assert tok not in lower, (
            f"lower-body / footwear token {tok!r} leaked into portrait "
            f"wire prompt — v1.71.2 filter regressed.\n{prompt!r}"
        )


def test_singapore_full_body_keeps_trousers_in_wire_prompt():
    """Symmetric check: full_body keeps the full outfit so the model
    knows what to render for the lower body."""
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.DATING,
        style="singapore_marina_bay",
        gender="male",
        framing="full_body",
    )
    assert "trousers" in prompt.lower(), (
        f"trousers stripped on full_body — v1.71.2 filter should pass "
        f"through.\n{prompt!r}"
    )


def test_crop_directive_carries_no_forbidden_head_tokens():
    """Defensive check — v1.70 retired ``head-and-shoulders`` / ``bust
    shot`` / ``upper third`` etc. The v1.71.2 crop directive must
    NOT re-introduce any of them under a different name."""
    from src.services.style_lint import forbidden_head_tokens_in_prompt

    for framing in ("portrait", "half_body", "full_body"):
        line = _FRAMING_PROMPT_DIRECTIVES[framing]
        leaks = forbidden_head_tokens_in_prompt(line)
        assert leaks == [], (
            f"crop directive for {framing!r} carries head-anchor tokens "
            f"{leaks!r}: {line!r}"
        )
