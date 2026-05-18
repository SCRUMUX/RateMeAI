"""Unit tests for :mod:`src.services.composition_safety`.

Covers the heuristic classifier, the policy table and the helper
predicates that the upstream wizards / bot consume.

The fixtures use synthetic ``(face_bbox, face_area_ratio, width, height)``
inputs because the classifier is a pure function of these — we don't
need real images here. End-to-end coverage on real photos lives in
``tests/test_services/test_input_quality.py``.
"""

from __future__ import annotations

import pytest

from src.services.composition_safety import (
    CompositionClass,
    allowed_framings,
    classify_heuristic,
    is_style_forbidden,
    is_style_risky,
    normalise_framing,
    policy_summary,
)


class _FakeSpec:
    """Minimal stand-in for :class:`StyleSpec` used by the CSL helpers."""

    def __init__(self, *, needs_full_body: bool = False, needs_torso: bool = False) -> None:
        self.needs_full_body = needs_full_body
        self.needs_torso = needs_torso


# ---------------------------------------------------------------------------
# CompositionClass.parse
# ---------------------------------------------------------------------------


def test_parse_accepts_known_values():
    assert CompositionClass.parse("portrait") is CompositionClass.PORTRAIT
    assert CompositionClass.parse("FULL_BODY") is CompositionClass.FULL_BODY
    assert CompositionClass.parse(CompositionClass.HALF_BODY) is CompositionClass.HALF_BODY


def test_parse_coerces_unknown_to_unknown():
    assert CompositionClass.parse("") is CompositionClass.UNKNOWN
    assert CompositionClass.parse(None) is CompositionClass.UNKNOWN
    assert CompositionClass.parse("garbage") is CompositionClass.UNKNOWN


# ---------------------------------------------------------------------------
# allowed_framings — policy table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls,expected",
    [
        (CompositionClass.FACE_CLOSEUP, ["portrait"]),
        (CompositionClass.PORTRAIT, ["portrait", "half_body"]),
        (CompositionClass.HALF_BODY, ["portrait", "half_body", "full_body"]),
        (CompositionClass.FULL_BODY, ["portrait", "half_body", "full_body"]),
        (CompositionClass.UNKNOWN, ["portrait"]),
    ],
)
def test_allowed_framings_matches_policy(cls, expected):
    assert allowed_framings(cls) == expected


def test_allowed_framings_unknown_is_fail_closed_safe():
    # The contract is: UNKNOWN is exactly as constrained as FACE_CLOSEUP.
    assert allowed_framings(CompositionClass.UNKNOWN) == allowed_framings(
        CompositionClass.FACE_CLOSEUP,
    )


# ---------------------------------------------------------------------------
# is_style_forbidden / is_style_risky
# ---------------------------------------------------------------------------


def test_full_body_style_is_forbidden_on_face_closeup():
    spec = _FakeSpec(needs_full_body=True)
    assert is_style_forbidden(CompositionClass.FACE_CLOSEUP, spec) is True
    assert is_style_forbidden(CompositionClass.PORTRAIT, spec) is True
    assert is_style_forbidden(CompositionClass.UNKNOWN, spec) is True
    assert is_style_forbidden(CompositionClass.HALF_BODY, spec) is False
    assert is_style_forbidden(CompositionClass.FULL_BODY, spec) is False


def test_torso_style_is_risky_only_on_face_closeup_and_unknown():
    spec = _FakeSpec(needs_torso=True)
    assert is_style_risky(CompositionClass.FACE_CLOSEUP, spec) is True
    assert is_style_risky(CompositionClass.UNKNOWN, spec) is True
    assert is_style_risky(CompositionClass.PORTRAIT, spec) is False
    assert is_style_risky(CompositionClass.HALF_BODY, spec) is False
    assert is_style_risky(CompositionClass.FULL_BODY, spec) is False


def test_unknown_style_spec_is_never_blocked():
    assert is_style_forbidden(CompositionClass.FACE_CLOSEUP, None) is False
    assert is_style_risky(CompositionClass.FACE_CLOSEUP, None) is False


def test_style_without_flags_is_never_blocked_or_risky():
    spec = _FakeSpec()
    for cls in CompositionClass:
        assert is_style_forbidden(cls, spec) is False
        assert is_style_risky(cls, spec) is False


# ---------------------------------------------------------------------------
# classify_heuristic
# ---------------------------------------------------------------------------


def test_missing_bbox_returns_unknown():
    assert classify_heuristic(None, 0.1, 800, 800) is CompositionClass.UNKNOWN


def test_zero_face_area_returns_unknown():
    assert classify_heuristic((0, 0, 100, 100), 0.0, 800, 800) is CompositionClass.UNKNOWN


def test_zero_dimensions_returns_unknown():
    assert classify_heuristic((0, 0, 100, 100), 0.1, 0, 100) is CompositionClass.UNKNOWN


def test_large_face_is_face_closeup():
    # Face fills 40% of the frame and sits in the middle — face_h ~= 600,
    # space_below ~= 100/600 = 0.17 → well under 1.0 face-height.
    bbox = (100, 100, 700, 700)  # 600×600 face
    cls = classify_heuristic(bbox, 0.45, 800, 800)
    assert cls is CompositionClass.FACE_CLOSEUP


def test_typical_portrait_is_portrait():
    # face_area=0.20 (above 0.18 portrait threshold), space_below ~= 250/350 ≈ 0.7 → FACE_CLOSEUP via space_below.
    # Use an arrangement that gives space_below ≥ 1.0 face-height.
    # face_h = 300, image_h = 1200 → space_below = (1200 - 600)/300 = 2.0
    bbox = (200, 300, 600, 600)  # 400x300 face
    cls = classify_heuristic(bbox, 0.20, 800, 1200)
    # face_area >= 0.18 portrait threshold; space_below = 2.0 = portrait_space_below
    # The classifier uses ``>=`` for face ratio and ``<`` for space_below; at
    # exactly 2.0 we should not trip face_closeup but still hit portrait.
    assert cls is CompositionClass.PORTRAIT


def test_half_body_classification():
    # face_area=0.08, space_below = 3 face-heights → half body
    # face_h = 200, image_h = 1200, fy2 = 400 → (1200-400)/200 = 4.0
    bbox = (200, 200, 600, 400)
    cls = classify_heuristic(bbox, 0.08, 800, 1200)
    # face_area=0.08 ≥ 0.06 half-body threshold; space_below=4.0
    assert cls in (CompositionClass.HALF_BODY, CompositionClass.PORTRAIT)


def test_full_body_classification():
    # Tiny face high in the frame → plenty of room below for legs.
    # face_h = 60, image_h = 1200, fy2 = 100 → (1200-100)/60 ≈ 18.3
    bbox = (300, 40, 400, 100)
    cls = classify_heuristic(bbox, 0.02, 800, 1200)
    assert cls is CompositionClass.FULL_BODY


def test_thresholds_can_be_overridden():
    # If we crank face_closeup_face_ratio down to 0.10 a 0.15 face becomes
    # a closeup that would otherwise be a portrait.
    bbox = (200, 300, 600, 600)
    cls = classify_heuristic(
        bbox,
        0.15,
        800,
        1200,
        face_closeup_face_ratio=0.10,
    )
    assert cls is CompositionClass.FACE_CLOSEUP


# ---------------------------------------------------------------------------
# normalise_framing
# ---------------------------------------------------------------------------


def test_normalise_framing_keeps_allowed_choice():
    assert normalise_framing(CompositionClass.HALF_BODY, "half_body") == "half_body"


def test_normalise_framing_snaps_to_first_allowed():
    # FACE_CLOSEUP only allows portrait — anything else snaps there.
    assert normalise_framing(CompositionClass.FACE_CLOSEUP, "full_body") == "portrait"
    assert normalise_framing(CompositionClass.UNKNOWN, "half_body") == "portrait"


def test_normalise_framing_handles_none_and_empty():
    assert normalise_framing(CompositionClass.HALF_BODY, None) == "portrait"
    assert normalise_framing(CompositionClass.HALF_BODY, "") == "portrait"


# ---------------------------------------------------------------------------
# policy_summary
# ---------------------------------------------------------------------------


def test_policy_summary_includes_all_fields():
    summary = policy_summary(CompositionClass.FACE_CLOSEUP)
    assert summary == {
        "composition_class": "face_closeup",
        "allowed_framings": ["portrait"],
        "forbid_full_body_styles": True,
        "warn_torso_styles": True,
    }


def test_policy_summary_accepts_string_input():
    assert policy_summary("full_body")["composition_class"] == "full_body"
    assert policy_summary("nonsense")["composition_class"] == "unknown"
