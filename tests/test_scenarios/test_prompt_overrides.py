"""Test that ``PromptEngine.build_image_prompt`` injects the scenario
``image_instructions`` override.

We rely on the helper ``_scenario_image_overrides`` in
:mod:`src.prompts.engine`, which reads from the scenarios registry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
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
                        "prompt_overrides": {
                            "analysis_checklist": [],
                            "image_instructions": "VISA_TEST_INSTRUCTION_TOKEN",
                        },
                        "enabled": True,
                    },
                    "visa-disabled": {
                        "kind": "visa",
                        "api_mode": "cv",
                        "prompt_overrides": {
                            "image_instructions": "DISABLED_TOKEN",
                        },
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


def test_build_image_prompt_appends_override(isolated_scenarios_file):
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV,
        style="visa_schengen",
        base_description="a person",
        gender="male",
        scenario_slug="visa-test",
    )
    assert "VISA_TEST_INSTRUCTION_TOKEN" in prompt


def test_build_image_prompt_omits_when_no_slug(isolated_scenarios_file):
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV,
        style="visa_schengen",
        base_description="a person",
        gender="male",
    )
    assert "VISA_TEST_INSTRUCTION_TOKEN" not in prompt


def test_build_image_prompt_skips_disabled_scenario(isolated_scenarios_file):
    engine = PromptEngine()
    prompt = engine.build_image_prompt(
        AnalysisMode.CV,
        style="visa_schengen",
        base_description="a person",
        gender="male",
        scenario_slug="visa-disabled",
    )
    assert "DISABLED_TOKEN" not in prompt
