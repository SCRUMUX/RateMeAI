"""Tests for history score_after resolution.

Guards against regressions where the Storage gallery shows the
pre-generation baseline instead of the actual post-gen score: the
selector must prefer `score_after`, then `delta.<mode_key>.post`, and
only fall back to the flat top-level fields for legacy rows.
"""

from __future__ import annotations

import pytest

from src.api.v1.tasks import _extract_history_score_after


def test_prefers_explicit_score_after():
    result = {
        "score_after": 8.42,
        "dating_score": 6.0,
        "delta": {"dating_score": {"pre": 6.0, "post": 8.42, "delta": 0.62}},
    }
    assert _extract_history_score_after(result, "dating") == pytest.approx(8.42)


def test_falls_back_to_delta_post_for_dating():
    result = {
        "dating_score": 6.0,
        "delta": {"dating_score": {"pre": 6.0, "post": 8.42, "delta": 0.62}},
    }
    assert _extract_history_score_after(result, "dating") == pytest.approx(8.42)


def test_falls_back_to_delta_post_for_social():
    result = {
        "social_score": 5.5,
        "delta": {"social_score": {"pre": 5.5, "post": 7.9, "delta": 0.62}},
    }
    assert _extract_history_score_after(result, "social") == pytest.approx(7.9)


def test_cv_averages_delta_post_across_three_metrics():
    result = {
        "trust": 6.0,
        "competence": 6.1,
        "hireability": 6.2,
        "delta": {
            "trust": {"pre": 6.0, "post": 8.2, "delta": 0.62},
            "competence": {"pre": 6.1, "post": 8.4, "delta": 0.62},
            "hireability": {"pre": 6.2, "post": 8.0, "delta": 0.62},
        },
    }
    expected = round((8.2 + 8.4 + 8.0) / 3, 2)
    assert _extract_history_score_after(result, "cv") == pytest.approx(expected)


def test_legacy_row_without_delta_falls_back_to_flat_field():
    result = {"dating_score": 7.34}
    assert _extract_history_score_after(result, "dating") == pytest.approx(7.34)


def test_legacy_cv_row_averages_flat_fields():
    result = {"trust": 7.0, "competence": 8.0, "hireability": 6.0}
    expected = round((7.0 + 8.0 + 6.0) / 3, 2)
    assert _extract_history_score_after(result, "cv") == pytest.approx(expected)


def test_returns_none_when_no_score_anywhere():
    assert _extract_history_score_after({}, "dating") is None
    assert _extract_history_score_after({}, "cv") is None


def test_empty_delta_dict_is_ignored():
    """`delta` present but empty / wrong shape must not crash; flat fields take over."""
    result = {"dating_score": 6.5, "delta": {}}
    assert _extract_history_score_after(result, "dating") == pytest.approx(6.5)

    result2 = {"dating_score": 6.5, "delta": {"dating_score": None}}
    assert _extract_history_score_after(result2, "dating") == pytest.approx(6.5)
