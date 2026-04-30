"""Unit tests for :mod:`src.services.style_lint`.

The lint engine is pure — every test is a single dict in, list of
issue codes out. No fixtures needed beyond the imported helpers.
"""

from __future__ import annotations

from src.services.style_lint import find_conflicts, lint_style


def _codes(issues: list[dict]) -> list[str]:
    return [str(i["code"]) for i in issues]


# ---------------------------------------------------------------------------
# lint_style — happy paths and clean catalog
# ---------------------------------------------------------------------------


def test_clean_v3_style_yields_no_issues():
    entry = {
        "id": "clean",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["round wall mirror in frame"],
        "scene_anchor": "minimalist apartment with neutral walls",
        "available_channels": ["lighting", "time_of_day"],
        "location_type": "indoor",
        "ambient": {
            "lighting": ["soft ambient", "warm directional"],
            "time_of_day": ["morning", "evening"],
        },
    }
    assert lint_style(entry) == []


def test_v1_style_skips_v3_specific_rules():
    """A pre-migration entry must not produce false positives."""
    entry = {
        "id": "legacy",
        "mode": "cv",
        "display_label": "Legacy",
        "hook_text": "old style",
    }
    issues = lint_style(entry)
    assert _codes(issues) == []


# ---------------------------------------------------------------------------
# TRIGGER_DIRTY — the user's headline complaint
# ---------------------------------------------------------------------------


def test_trigger_with_full_length_word_flags_framing_leak():
    entry = {
        "id": "mirror_aesthetic",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": [
            "round wall mirror in frame",
            "full-length mirror reflection",  # framing leak
            "tall standing mirror anchoring the scene",  # framing leak
        ],
        "scene_anchor": "minimalist apartment",
    }
    codes = _codes(lint_style(entry))
    assert codes.count("TRIGGER_DIRTY") == 2


def test_trigger_with_lighting_word_flags_lighting_leak():
    entry = {
        "id": "noir",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["alley with rim light at midnight"],
        "scene_anchor": "downtown alley",
    }
    codes = _codes(lint_style(entry))
    assert "TRIGGER_DIRTY" in codes


def test_trigger_with_weather_word_flags_weather_leak():
    entry = {
        "id": "umbrella",
        "schema_version": 3,
        "mode": "dating",
        "trigger_pool": ["holding an umbrella in the rain"],
        "scene_anchor": "urban street",
    }
    codes = _codes(lint_style(entry))
    assert "TRIGGER_DIRTY" in codes


# ---------------------------------------------------------------------------
# INDOOR_SEASON / INDOOR_WEATHER — the user's second complaint
# ---------------------------------------------------------------------------


def test_indoor_with_season_channel_is_error():
    entry = {
        "id": "lobby",
        "schema_version": 3,
        "mode": "cv",
        "trigger_pool": ["modern hotel lobby reception desk"],
        "scene_anchor": "hotel lobby",
        "location_type": "indoor",
        "available_channels": ["lighting", "season"],
        "ambient": {"lighting": ["warm"], "season": ["spring", "summer", "autumn", "winter"]},
    }
    issues = lint_style(entry)
    codes = _codes(issues)
    assert "INDOOR_SEASON" in codes
    assert any(i["severity"] == "error" for i in issues if i["code"] == "INDOOR_SEASON")


def test_indoor_with_weather_channel_is_error():
    entry = {
        "id": "office",
        "schema_version": 3,
        "mode": "cv",
        "trigger_pool": ["corporate office workspace"],
        "scene_anchor": "modern office",
        "location_type": "indoor",
        "available_channels": ["weather"],
        "ambient": {"weather": ["clear", "overcast"]},
    }
    assert "INDOOR_WEATHER" in _codes(lint_style(entry))


def test_outdoor_with_season_is_clean():
    entry = {
        "id": "burj",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["Burj Khalifa silhouette behind"],
        "scene_anchor": "rooftop terrace overlooking the marina",
        "location_type": "outdoor",
        "available_channels": ["lighting", "weather", "time_of_day", "season"],
        "ambient": {
            "lighting": ["warm cinematic"],
            "weather": ["clear"],
            "time_of_day": ["evening"],
            "season": ["spring", "summer", "autumn", "winter"],
        },
    }
    assert lint_style(entry) == []


# ---------------------------------------------------------------------------
# DOCUMENT_AMBIENT
# ---------------------------------------------------------------------------


def test_document_with_lighting_channel_is_error():
    entry = {
        "id": "passport_rf",
        "schema_version": 3,
        "mode": "cv",
        "trigger_pool": ["passport photo"],
        "scene_anchor": "neutral background passport photo",
        "location_type": "document",
        "available_channels": ["lighting"],
        "ambient": {"lighting": ["even neutral"]},
    }
    assert "DOCUMENT_AMBIENT" in _codes(lint_style(entry))


# ---------------------------------------------------------------------------
# SEASON_INCOMPLETE — 4 seasons required when channel enabled
# ---------------------------------------------------------------------------


def test_season_pool_with_two_entries_is_warning():
    entry = {
        "id": "burj_partial",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["Burj Khalifa skyline"],
        "scene_anchor": "rooftop terrace",
        "location_type": "outdoor",
        "available_channels": ["season"],
        "ambient": {"season": ["spring", "autumn"]},
    }
    issues = lint_style(entry)
    codes = _codes(issues)
    assert "SEASON_INCOMPLETE" in codes
    incomplete = [i for i in issues if i["code"] == "SEASON_INCOMPLETE"][0]
    assert incomplete["severity"] == "warning"
    assert set(incomplete["detail"]["missing"]) == {"summer", "winter"}


def test_season_pool_with_all_four_is_clean():
    entry = {
        "id": "park",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["urban park stroll"],
        "scene_anchor": "tree-lined park",
        "location_type": "outdoor",
        "available_channels": ["season"],
        "ambient": {"season": ["spring", "summer", "autumn", "winter"]},
    }
    assert "SEASON_INCOMPLETE" not in _codes(lint_style(entry))


# ---------------------------------------------------------------------------
# EMPTY_POOL — channel enabled but no entries
# ---------------------------------------------------------------------------


def test_lighting_enabled_with_empty_pool_is_error():
    entry = {
        "id": "broken",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["something"],
        "scene_anchor": "anywhere",
        "available_channels": ["lighting"],
        "ambient": {"lighting": []},
    }
    codes = _codes(lint_style(entry))
    assert "EMPTY_POOL" in codes


# ---------------------------------------------------------------------------
# UNKNOWN_CHANNEL / UNKNOWN_LOCATION — schema typos
# ---------------------------------------------------------------------------


def test_unknown_channel_is_error():
    entry = {
        "id": "typo",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["x"],
        "scene_anchor": "x",
        "available_channels": ["lihting"],  # typo
    }
    assert "UNKNOWN_CHANNEL" in _codes(lint_style(entry))


def test_unknown_location_is_error():
    entry = {
        "id": "weird",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["x"],
        "scene_anchor": "x",
        "location_type": "underwater",
    }
    assert "UNKNOWN_LOCATION" in _codes(lint_style(entry))


def test_empty_location_is_clean():
    """Unclassified styles must not trigger location-sensitive rules."""
    entry = {
        "id": "untyped",
        "schema_version": 3,
        "mode": "social",
        "trigger_pool": ["x"],
        "scene_anchor": "x",
        "location_type": "",
        "available_channels": ["season"],
        "ambient": {"season": ["spring", "summer", "autumn", "winter"]},
    }
    codes = _codes(lint_style(entry))
    assert "INDOOR_SEASON" not in codes
    assert "DOCUMENT_AMBIENT" not in codes
    assert "UNKNOWN_LOCATION" not in codes


# ---------------------------------------------------------------------------
# find_conflicts — duplicates / similar / duplicate ids
# ---------------------------------------------------------------------------


def test_duplicate_labels_grouped_with_emoji_normalisation():
    rows = [
        {"id": "office_1", "display_label": "🏢 В офисе"},
        {"id": "office_2", "display_label": "В офисе"},
        {"id": "park", "display_label": "🌳 В парке"},
    ]
    report = find_conflicts(rows)
    assert len(report["duplicate_labels"]) == 1
    dup = report["duplicate_labels"][0]
    assert dup["normalised"] == "в офисе"
    assert sorted(dup["ids"]) == ["office_1", "office_2"]


def test_similar_labels_pick_up_levenshtein_close_pairs():
    rows = [
        {"id": "a", "display_label": "В офисе"},
        {"id": "b", "display_label": "В офисах"},  # distance 1
        {"id": "c", "display_label": "В парке"},
    ]
    report = find_conflicts(rows)
    pair_ids = {(r["id_a"], r["id_b"]) for r in report["similar_labels"]}
    assert ("a", "b") in pair_ids
    assert all(r["id_a"] != "c" and r["id_b"] != "c" for r in report["similar_labels"])


def test_duplicate_labels_excluded_from_similar_bucket():
    rows = [
        {"id": "x", "display_label": "🏢 Office"},
        {"id": "y", "display_label": "Office"},  # same after normalisation
    ]
    report = find_conflicts(rows)
    assert report["duplicate_labels"]
    assert report["similar_labels"] == []


def test_duplicate_ids_reported():
    rows = [
        {"id": "twin", "display_label": "A"},
        {"id": "twin", "display_label": "B"},
    ]
    report = find_conflicts(rows)
    assert report["duplicate_ids"] == ["twin"]


def test_clean_catalog_is_all_empty_buckets():
    rows = [
        {"id": "alpha", "display_label": "Alpha"},
        {"id": "bravo", "display_label": "Bravo"},
        {"id": "charlie", "display_label": "Charlie"},
    ]
    report = find_conflicts(rows)
    assert report == {"duplicate_labels": [], "similar_labels": [], "duplicate_ids": []}
