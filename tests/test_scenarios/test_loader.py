"""Loader / registry tests for the Scenario Engine.

We point ``scenarios.loader.SCENARIOS_PATH`` at a tmp JSON file and
exercise the public ``load_scenarios`` / ``get_scenario`` /
``list_scenarios`` API directly. No DB, no FastAPI app.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.enums import AnalysisMode
from src.scenarios import (
    Scenario,
    get_scenario,
    list_enabled_scenarios,
    list_scenarios,
)
from src.scenarios import loader as scenarios_loader


@pytest.fixture
def isolated_scenarios_file(tmp_path: Path, monkeypatch):
    fake_path = tmp_path / "scenarios.json"
    fake_path.write_text(
        json.dumps(
            {
                "scenarios": {
                    "visa-test": {
                        "kind": "visa",
                        "api_mode": "cv",
                        "pipeline_profile": "simple",
                        "step3_mode": "document_formats",
                        "output_spec": {
                            "size_mm": [35, 45],
                            "dpi": 300,
                            "background_color": "#FFFFFF",
                            "head_height_mm": [32, 36],
                            "aspect_key": "visa_test",
                        },
                        "requirements": {
                            "expression": "neutral",
                            "glasses": "no_tinted",
                            "head_covering": "forbidden_except_religious",
                            "background": "uniform_white",
                            "shadows": "forbidden",
                            "compliance_source": "https://example.com/spec",
                        },
                        "prompt_overrides": {
                            "analysis_checklist": ["check 1", "check 2"],
                            "image_instructions": "Document-grade portrait.",
                        },
                        "paywall": {"pack_qty": 5, "show_paywall": True},
                        "landing_slug": "visa-test",
                        "enabled": True,
                    },
                    "core-disabled": {
                        "kind": "core",
                        "api_mode": "dating",
                        "enabled": False,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scenarios_loader, "SCENARIOS_PATH", fake_path)
    scenarios_loader.invalidate_cache()
    yield fake_path
    scenarios_loader.invalidate_cache()


def test_load_scenarios_parses_visa_record(isolated_scenarios_file):
    scenarios = scenarios_loader.load_scenarios()
    assert "visa-test" in scenarios
    s: Scenario = scenarios["visa-test"]
    assert s.kind == "visa"
    assert s.api_mode == AnalysisMode.CV
    assert s.pipeline_profile == "simple"
    assert s.step3_mode == "document_formats"
    assert s.output_spec is not None
    assert s.output_spec.size_mm == (35.0, 45.0)
    assert s.output_spec.aspect_key == "visa_test"
    assert s.requirements is not None
    assert s.requirements.glasses == "no_tinted"
    assert s.prompt_overrides is not None
    assert s.prompt_overrides.analysis_checklist == ("check 1", "check 2")
    assert s.paywall is not None
    assert s.paywall.pack_qty == 5
    assert s.enabled is True


def test_get_scenario_returns_none_for_unknown(isolated_scenarios_file):
    assert get_scenario("does-not-exist") is None


def test_list_enabled_scenarios_filters_disabled(isolated_scenarios_file):
    enabled = list_enabled_scenarios()
    slugs = {s.slug for s in enabled}
    assert "visa-test" in slugs
    assert "core-disabled" not in slugs


def test_list_scenarios_filters_by_kind(isolated_scenarios_file):
    visa_scenarios = list_scenarios(kind="visa")
    assert all(s.kind == "visa" for s in visa_scenarios)
    assert {s.slug for s in visa_scenarios} == {"visa-test"}


def test_to_public_dict_strips_prompt_overrides(isolated_scenarios_file):
    s = get_scenario("visa-test")
    assert s is not None
    public = s.to_public_dict()
    assert "prompt_overrides" not in public
    assert "requirements" not in public
    assert public["slug"] == "visa-test"
    assert public["api_mode"] == "cv"
    assert public["output_spec"]["aspect_key"] == "visa_test"
    assert public["paywall"] == {"pack_qty": 5, "show_paywall": True}


def test_invalidate_cache_picks_up_disk_changes(isolated_scenarios_file):
    scenarios_loader.load_scenarios()
    isolated_scenarios_file.write_text(
        json.dumps({"scenarios": {}}), encoding="utf-8"
    )
    scenarios_loader.invalidate_cache()
    assert scenarios_loader.load_scenarios() == {}


def test_missing_file_returns_empty_registry(tmp_path: Path, monkeypatch):
    fake_path = tmp_path / "missing.json"
    monkeypatch.setattr(scenarios_loader, "SCENARIOS_PATH", fake_path)
    scenarios_loader.invalidate_cache()
    try:
        assert scenarios_loader.load_scenarios() == {}
    finally:
        scenarios_loader.invalidate_cache()
