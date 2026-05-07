"""Tests for ``src/services/visa_compliance.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.scenarios import loader as scenarios_loader
from src.services.visa_compliance import (
    compliance_checklist,
    output_spec_payload,
)


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
                        "prompt_overrides": {
                            "analysis_checklist": ["rule a", "rule b"],
                            "image_instructions": "x",
                        },
                        "enabled": True,
                    },
                    "core-photo": {
                        "kind": "core",
                        "api_mode": "dating",
                        "enabled": True,
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


def test_compliance_checklist_returns_pending_pairs(isolated_scenarios_file):
    items = compliance_checklist("visa-test")
    assert items == [
        {"rule": "rule a", "status": "pending"},
        {"rule": "rule b", "status": "pending"},
    ]


def test_compliance_checklist_empty_for_non_visa(isolated_scenarios_file):
    assert compliance_checklist("core-photo") == []


def test_compliance_checklist_empty_for_unknown(isolated_scenarios_file):
    assert compliance_checklist("does-not-exist") == []


def test_compliance_checklist_empty_for_none_slug(isolated_scenarios_file):
    assert compliance_checklist(None) == []


def test_output_spec_payload_for_visa(isolated_scenarios_file):
    payload = output_spec_payload("visa-test")
    assert payload == {
        "size_mm": [35.0, 45.0],
        "dpi": 300,
        "background_color": "#FFFFFF",
        "head_height_mm": [32.0, 36.0],
        "aspect_key": "visa_test",
    }


def test_output_spec_payload_none_for_core(isolated_scenarios_file):
    assert output_spec_payload("core-photo") is None
