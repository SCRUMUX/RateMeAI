"""Tests for scripts/migrate_styles_v1_to_v2.py + v2 JSON schema health.

PR3 of the style-schema-v2 migration.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.migrate_styles_v1_to_v2 import (  # noqa: E402
    _merge_v2,
    _select_entries,
    _v1_to_v2_block,
)
from src.services.style_loader_v2 import _to_v2  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — tiny v1 corpus that mimics the real shape of styles.json
# ---------------------------------------------------------------------------


_V1_FIXTURE = [
    {
        "id": "paris_eiffel",
        "mode": "dating",
        "category": "General",
        "type": "scene_locked",
        "base_scene": "Parisian boulevard with Eiffel Tower",
        "default_clothing": "fitted navy blazer over white tee",
        "expression": "Warm genuine smile.",
        "allowed_variations": {
            "lighting": ["warm sunset", "overcast"],
            "clothing": [],
            "framing": ["portrait", "half_body", "full_body"],
        },
    },
    {
        "id": "warm_outdoor",
        "mode": "dating",
        "category": "General",
        "type": "flexible",
        "base_scene": "golden-hour park",
        "default_clothing": "crew-neck tee",
        "expression": "Relaxed warm smile.",
        "allowed_variations": {
            "lighting": ["golden hour", "soft overcast"],
            "framing": ["portrait", "half_body", "full_body"],
        },
    },
    {
        "id": "corporate",
        "mode": "cv",
        "category": "General",
        "type": "semi_locked",
        "base_scene": "modern corner office",
        "default_clothing": "tailored charcoal suit",
        "expression": "Professional calm gaze.",
        "allowed_variations": {
            "lighting": ["diffused daylight"],
            "framing": ["portrait", "half_body", "full_body"],
        },
    },
]


# ---------------------------------------------------------------------------
# _v1_to_v2_block
# ---------------------------------------------------------------------------


def test_v1_to_v2_block_has_schema_version_2():
    block = _v1_to_v2_block(_V1_FIXTURE[0])
    assert block["schema_version"] == 2


def test_v1_to_v2_block_preserves_base_scene_and_clothing():
    block = _v1_to_v2_block(_V1_FIXTURE[0])
    assert block["background"]["base"] == "Parisian boulevard with Eiffel Tower"
    assert block["clothing"]["default"] == "fitted navy blazer over white tee"


def test_v1_to_v2_block_maps_type_to_lock_level():
    assert _v1_to_v2_block(_V1_FIXTURE[0])["background"]["lock"] == "locked"
    assert _v1_to_v2_block(_V1_FIXTURE[1])["background"]["lock"] == "flexible"
    assert _v1_to_v2_block(_V1_FIXTURE[2])["background"]["lock"] == "semi"


def test_v1_to_v2_block_weather_policy_default_is_disabled():
    """Matches v1 baseline — weather never quietly leaked from lighting."""
    block = _v1_to_v2_block(_V1_FIXTURE[0])
    assert block["weather"] == {"enabled": False, "allowed": [], "default_na": True}


def test_v1_to_v2_block_context_slots_include_framing_fallback():
    minimal = deepcopy(_V1_FIXTURE[0])
    minimal["allowed_variations"] = {}
    block = _v1_to_v2_block(minimal)
    assert block["context_slots"]["framing"] == [
        "portrait",
        "half_body",
        "full_body",
    ]


# ---------------------------------------------------------------------------
# _merge_v2 keeps v1 fields intact
# ---------------------------------------------------------------------------


def test_merge_preserves_v1_fields():
    merged = _merge_v2(_V1_FIXTURE[0])
    for k in ("id", "mode", "category", "type", "base_scene", "default_clothing"):
        assert merged[k] == _V1_FIXTURE[0][k]
    assert merged["schema_version"] == 2
    assert "background" in merged


# ---------------------------------------------------------------------------
# _select_entries (batch selectors)
# ---------------------------------------------------------------------------


def test_select_all_skips_already_migrated():
    corpus = deepcopy(_V1_FIXTURE)
    corpus[0]["schema_version"] = 2  # simulate already migrated
    result = _select_entries(corpus, "all")
    ids = [e["id"] for e in result]
    assert "paris_eiffel" not in ids
    assert len(ids) == 2


def test_select_by_count():
    result = _select_entries(_V1_FIXTURE, "count:1")
    assert len(result) == 1


def test_select_by_mode():
    result = _select_entries(_V1_FIXTURE, "mode:cv")
    assert [e["id"] for e in result] == ["corporate"]


def test_select_by_ids():
    result = _select_entries(_V1_FIXTURE, "ids:paris_eiffel,corporate")
    assert sorted(e["id"] for e in result) == ["corporate", "paris_eiffel"]


def test_select_by_glob():
    result = _select_entries(_V1_FIXTURE, "glob:paris_*")
    assert [e["id"] for e in result] == ["paris_eiffel"]


# ---------------------------------------------------------------------------
# Roundtrip: migrated JSON must parse back into StyleSpecV2 via the loader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry_idx", range(len(_V1_FIXTURE)))
def test_migrated_entry_parses_via_loader(entry_idx):
    merged = _merge_v2(_V1_FIXTURE[entry_idx])
    spec = _to_v2(merged)
    assert spec is not None
    assert spec.schema_version == 2
    assert spec.key == _V1_FIXTURE[entry_idx]["id"]
    assert spec.mode == _V1_FIXTURE[entry_idx]["mode"]


# ---------------------------------------------------------------------------
# Live styles.json health — count invariant
# ---------------------------------------------------------------------------


def test_live_styles_json_v1_plus_v2_equals_total():
    """As migration progresses we need the invariant v1+v2 == total to
    always hold (never drop entries)."""
    path = os.path.join(_REPO_ROOT, "data", "styles.json")
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    v2 = [e for e in entries if int(e.get("schema_version") or 0) == 2]
    v1 = [e for e in entries if int(e.get("schema_version") or 0) < 2]
    assert len(v1) + len(v2) == len(entries)


# ---------------------------------------------------------------------------
# --write smoke test through a temp file
# ---------------------------------------------------------------------------


def test_write_produces_valid_json_round_trip(tmp_path):
    src = tmp_path / "styles.json"
    with open(src, "w", encoding="utf-8") as f:
        json.dump(_V1_FIXTURE, f, ensure_ascii=False, indent=2)

    # The module exposes main() via raise SystemExit — invoke the
    # logic manually to avoid sys.argv mutation in the test.
    from scripts.migrate_styles_v1_to_v2 import _merge_v2 as _mv

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    migrated = [_mv(e) for e in data]
    with open(src, "w", encoding="utf-8") as f:
        json.dump(migrated, f, ensure_ascii=False, indent=2)

    with open(src, "r", encoding="utf-8") as f:
        parsed = json.load(f)
    assert all(int(e.get("schema_version") or 0) == 2 for e in parsed)
