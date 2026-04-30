"""Unit tests for the v3 ``resolved_slots`` projection used by the
history endpoint (prompt-pipeline-overhaul follow-up A1, May 2026).

The history payload exposes a curated subset of the slot map written
by the v3 prompt pipeline. We test the helper directly so the
contract (whitelisted keys, length cap, gracefully ignored garbage)
stays pinned even without the API integration test infrastructure
(PG / Redis) that ``tests/test_api/test_analyze.py`` requires.
"""

from __future__ import annotations

from src.api.v1.tasks import _project_resolved_slots


def test_returns_none_for_missing_field():
    assert _project_resolved_slots(None) is None


def test_returns_none_for_empty_dict():
    assert _project_resolved_slots({}) is None


def test_returns_none_for_non_dict_garbage():
    # The executor writes a dict; defensive code should still survive
    # if a worker version ever writes a string / list.
    assert _project_resolved_slots("trigger=mirror") is None
    assert _project_resolved_slots(["mirror"]) is None
    assert _project_resolved_slots(42) is None


def test_keeps_only_whitelisted_keys():
    raw = {
        "trigger": "full-length mirror reflection",
        "lighting": "warm cinematic",
        "weather": "clear",
        "time_of_day": "evening",
        "season": "autumn",
        "clothing": "smart casual",
        # Keys that exist in ResolvedSlots but stay server-side:
        "random_picks": {"lighting": "warm cinematic"},
        "user_overrides": {},
        "substitutions": [],
    }
    out = _project_resolved_slots(raw)
    assert out is not None
    # Whitelisted keys round-trip.
    assert out["trigger"] == "full-length mirror reflection"
    assert out["lighting"] == "warm cinematic"
    assert out["weather"] == "clear"
    assert out["time_of_day"] == "evening"
    assert out["season"] == "autumn"
    assert out["clothing"] == "smart casual"
    # Server-side analytics fields must NOT leak to the FE — the
    # gallery has no business rendering ``substitutions`` or
    # ``random_picks``.
    assert "random_picks" not in out
    assert "user_overrides" not in out
    assert "substitutions" not in out


def test_drops_empty_string_channels():
    raw = {
        "trigger": "mirror",
        "lighting": "",
        "weather": "   ",
    }
    out = _project_resolved_slots(raw)
    assert out == {"trigger": "mirror"}


def test_drops_non_string_values():
    raw = {
        "trigger": "mirror",
        "lighting": 42,
        "weather": None,
        "season": ["autumn"],
    }
    out = _project_resolved_slots(raw)
    assert out == {"trigger": "mirror"}


def test_truncates_long_values_with_ellipsis():
    long_value = "x" * 500
    raw = {"trigger": long_value}
    out = _project_resolved_slots(raw)
    assert out is not None
    assert out["trigger"].endswith("…")
    # 240 char cap + 1 ellipsis char.
    assert len(out["trigger"]) <= 241


def test_returns_none_when_only_unknown_keys_present():
    # If the executor writes an entirely unrecognised shape (future
    # v4? rogue admin import?), the FE should render no badges
    # rather than show empty-string chips.
    raw = {"foo": "bar", "baz": "qux"}
    assert _project_resolved_slots(raw) is None
