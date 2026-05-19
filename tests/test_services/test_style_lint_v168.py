"""Unit tests for the v1.68 style-lint rules.

Two new codes added in v1.68:

* ``DOUBLED_WORD`` (error) — any string field carries an adjacent
  repeated word (``diffused diffused``, ``warm warm``, …). The
  2026_06_styles_cleanup migration auto-fixes existing instances;
  this rule is the regression guard.
* ``SCENE_LIGHTING_DUPLICATE`` (warning) — a lighting cue appears
  inside ``scene_anchor`` / ``base_scene`` while the ``lighting``
  channel is also enabled, which causes the wire prompt to carry
  two competing lighting recipes.

The lint runs against the live ``data/styles.json`` separately in
:func:`test_catalog_clean_after_migration` to verify the migration
left a clean catalog behind.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.services.style_lint import lint_style


def _codes(issues) -> list[str]:
    return [i["code"] for i in issues]


# ---------------------------------------------------------------------------
# DOUBLED_WORD
# ---------------------------------------------------------------------------


def test_doubled_word_fires_on_repeated_token_in_scene_anchor():
    raw = {
        "id": "fictional_doubled",
        "schema_version": 3,
        "scene_anchor": (
            "modern office, floor-to-ceiling windows with diffused diffused "
            "daylight, neutral beige wall"
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    codes = _codes(issues)
    assert "DOUBLED_WORD" in codes
    doubled = next(i for i in issues if i["code"] == "DOUBLED_WORD")
    assert doubled["severity"] == "error"
    assert doubled["detail"]["word"].lower() == "diffused"


def test_doubled_word_fires_on_nested_trigger_pool():
    raw = {
        "id": "fictional_pool_doubled",
        "schema_version": 3,
        "trigger_pool": [
            "polished marble lobby with warm warm tungsten lighting",
        ],
    }
    issues = lint_style(raw)
    codes = _codes(issues)
    assert "DOUBLED_WORD" in codes
    doubled = next(i for i in issues if i["code"] == "DOUBLED_WORD")
    assert doubled["field"].startswith("trigger_pool")


def test_doubled_word_clean_catalog_passes():
    raw = {
        "id": "fictional_clean",
        "schema_version": 3,
        "scene_anchor": (
            "modern office, floor-to-ceiling windows with diffused daylight, "
            "neutral beige wall"
        ),
        "trigger_pool": ["polished marble lobby with warm tungsten lighting"],
    }
    issues = lint_style(raw)
    assert "DOUBLED_WORD" not in _codes(issues)


# ---------------------------------------------------------------------------
# SCENE_LIGHTING_DUPLICATE
# ---------------------------------------------------------------------------


def test_scene_lighting_duplicate_fires_when_channel_enabled():
    """``scene_anchor`` says ``golden sunset`` AND ``lighting`` channel is on
    — the sampler will roll an extra lighting string and the prompt
    will carry two competing recipes.
    """
    raw = {
        "id": "fictional_rooftop_golden",
        "schema_version": 3,
        "scene_anchor": (
            "rooftop terrace with city skyline at golden sunset, "
            "distant lights"
        ),
        "trigger_pool": ["dummy"],
        "available_channels": ["lighting"],
        "ambient": {"lighting": ["warm sunset glow"]},
    }
    issues = lint_style(raw)
    codes = _codes(issues)
    assert "SCENE_LIGHTING_DUPLICATE" in codes
    leak = next(i for i in issues if i["code"] == "SCENE_LIGHTING_DUPLICATE")
    assert leak["severity"] == "warning"
    assert "golden sunset" in leak["detail"]["tokens"]


def test_scene_lighting_duplicate_quiet_when_channel_disabled():
    """``lighting`` channel OFF: the scene cue is the SOLE light
    directive, so the rule should stay quiet.
    """
    raw = {
        "id": "fictional_rooftop_no_channel",
        "schema_version": 3,
        "scene_anchor": (
            "rooftop terrace with city skyline at golden sunset, "
            "distant lights"
        ),
        "trigger_pool": ["dummy"],
        "available_channels": [],
    }
    issues = lint_style(raw)
    assert "SCENE_LIGHTING_DUPLICATE" not in _codes(issues)


# ---------------------------------------------------------------------------
# Catalog regression guard
# ---------------------------------------------------------------------------


_STYLES_PATH = Path(__file__).resolve().parents[2] / "data" / "styles.json"


def test_catalog_clean_after_v168_migration():
    """The 2026_06_styles_cleanup migration must leave zero
    ``DOUBLED_WORD`` errors in the live catalog. If this fails, the
    migration was either skipped or new doubled words were added
    after it ran — re-run the migration or fix the offending entry
    by hand.
    """
    entries = json.loads(_STYLES_PATH.read_text(encoding="utf-8"))
    offenders: list[tuple[str, str, str]] = []
    for entry in entries:
        sid = str(entry.get("id") or "<unknown>")
        for issue in lint_style(entry):
            if issue["code"] == "DOUBLED_WORD":
                offenders.append((sid, issue["field"],
                                  issue["detail"]["word"]))
    assert not offenders, (
        "DOUBLED_WORD found in live catalog after the v1.68 migration:\n"
        + "\n".join(
            f"  - {sid}.{field}: doubled {word!r}"
            for sid, field, word in offenders
        )
    )
