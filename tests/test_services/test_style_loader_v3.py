"""Stage 1 (prompt-pipeline-overhaul): style_loader_v3 unit tests.

Three contracts for the v3 loader:

1. Only entries with ``schema_version == 3`` are picked up; v1/v2
   entries are ignored.
2. Entries that lack a non-empty ``trigger_pool`` (and lack a legacy
   ``trigger`` to materialise one) are rejected with a log line; we
   never accidentally register a v3 spec without an inviolable
   trigger.
3. The feature flag gates registration globally — when off, the
   loader registers nothing even if v3 entries exist in the JSON.
"""

from __future__ import annotations

import pytest

from src.prompts.image_gen import STYLE_REGISTRY
from src.prompts.style_schema_v3 import StyleSpecV3
from src.services.style_loader_v3 import register_v3_styles_from_json


@pytest.fixture
def _registry_isolated():
    snap_v3 = dict(STYLE_REGISTRY._v3_by_key)
    STYLE_REGISTRY._v3_by_key.clear()
    yield
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_by_key.update(snap_v3)


def _v3_entry(**overrides) -> dict:
    base = {
        "id": "burj_khalifa",
        "mode": "social",
        "schema_version": 3,
        "trigger_pool": [
            "Burj Khalifa skyline at twilight",
            "Burj Khalifa lit at night",
        ],
        "scene_anchor": "open-air observation terrace overlooking Dubai",
        "scene_overrides": [
            "luxury rooftop bar overlooking downtown Dubai",
        ],
        "background_lock": "semi",
        "ambient": {
            "lighting": ["warm cinematic", "blue hour"],
            "weather": ["clear", "overcast"],
            "time_of_day": ["evening", "night"],
            "season": ["spring", "winter"],
        },
        "clothing": {
            "default": {
                "male": "suit",
                "female": "dress",
                "neutral": "smart casual",
            },
            "allowed": [],
            "gender_neutral": False,
        },
        "quality_identity": {"base": "", "per_model_tail": {}},
        "expression": "calm confident expression",
    }
    base.update(overrides)
    return base


def test_loader_registers_only_schema_v3_entries(monkeypatch, _registry_isolated):
    raw = [
        _v3_entry(),
        {"id": "v2_only", "mode": "social", "schema_version": 2},
        {"id": "v1_only", "mode": "social"},
    ]
    n = register_v3_styles_from_json(raw)
    assert n == 1
    spec = STYLE_REGISTRY.get_v3("social", "burj_khalifa")
    assert isinstance(spec, StyleSpecV3)
    assert spec.trigger_pool[0].startswith("Burj Khalifa")


def test_loader_is_always_on_post_v4_1(monkeypatch, _registry_isolated):
    """v4.1 (May 2026) removed the ``style_schema_v3_enabled`` flag —
    the v3 loader is always-on, so a fresh raw entry is always
    registered. The previous flag-off contract no longer applies.
    """
    n = register_v3_styles_from_json([_v3_entry()])
    assert n == 1
    assert STYLE_REGISTRY.get_v3("social", "burj_khalifa") is not None


def test_loader_rejects_entry_with_empty_trigger_pool(
    monkeypatch, _registry_isolated, caplog
):
    bad = _v3_entry(trigger_pool=[], trigger="")
    with caplog.at_level("ERROR"):
        n = register_v3_styles_from_json([bad])
    assert n == 0
    assert any("trigger_pool" in rec.message for rec in caplog.records)


def test_loader_materialises_legacy_trigger_into_pool(
    monkeypatch, _registry_isolated
):
    """For backwards-compatibility during the migration: if a v3 entry
    forgot to populate ``trigger_pool`` but still carries a legacy
    ``trigger`` string, the loader synthesises a pool of one."""
    entry = _v3_entry(trigger_pool=[], trigger="legacy mirror")
    n = register_v3_styles_from_json([entry])
    assert n == 1
    spec = STYLE_REGISTRY.get_v3("social", "burj_khalifa")
    assert spec is not None
    assert spec.trigger_pool == ("legacy mirror",)


def test_loader_rejects_entry_without_scene_anchor(
    monkeypatch, _registry_isolated, caplog
):
    bad = _v3_entry(scene_anchor="")
    with caplog.at_level("ERROR"):
        n = register_v3_styles_from_json([bad])
    assert n == 0
    assert any("scene_anchor" in rec.message for rec in caplog.records)


def test_loader_falls_back_to_base_scene_for_anchor(
    monkeypatch, _registry_isolated
):
    """``base_scene`` is the v2 spelling. When a v3 author re-uses the
    legacy field by mistake, the loader still picks it up."""
    entry = _v3_entry()
    entry.pop("scene_anchor")
    entry["base_scene"] = "fallback anchor"
    n = register_v3_styles_from_json([entry])
    assert n == 1
    spec = STYLE_REGISTRY.get_v3("social", "burj_khalifa")
    assert spec is not None
    assert spec.scene_anchor == "fallback anchor"


def test_loader_populates_ambient_pools(monkeypatch, _registry_isolated):
    register_v3_styles_from_json([_v3_entry()])
    spec = STYLE_REGISTRY.get_v3("social", "burj_khalifa")
    assert isinstance(spec, StyleSpecV3)
    assert spec.ambient.lighting == ("warm cinematic", "blue hour")
    assert spec.ambient.weather == ("clear", "overcast")
    assert spec.ambient.time_of_day == ("evening", "night")
    assert spec.ambient.season == ("spring", "winter")
