"""Tests for the approval-probability heuristic + AnalysisDisplay model.

Pure unit tests. No FastAPI app, no DB. We point the scenarios loader
at a tmp JSON file so the heuristic sees a deterministic registry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.scenarios import AnalysisDisplay, get_scenario, loader as scenarios_loader
from src.services.input_quality import InputQualityIssue, InputQualityReport
from src.services.visa_compliance import (
    estimate_approval_probability,
    is_approval_probability_scenario,
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
                        "analysis_display": {
                            "mode": "approval_probability",
                            "success_probability_after_pct": 98.9,
                            "label_key": "wizard.analysis.approvalProbability",
                        },
                        "enabled": True,
                    },
                    "document-photo": {
                        "kind": "document",
                        "api_mode": "cv",
                        "analysis_display": {
                            "mode": "approval_probability",
                            "success_probability_after_pct": 98.9,
                        },
                        "enabled": True,
                    },
                    "dating-photo": {
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


def _report(face_area: float, soft_warns: int = 0, blur_face: float = 100.0) -> InputQualityReport:
    soft = [
        InputQualityIssue(
            code=f"warn{i}", severity="warn", message="m", suggestion="s"
        )
        for i in range(soft_warns)
    ]
    return InputQualityReport(
        can_generate=True,
        issues=soft,
        face_area_ratio=face_area,
        blur_face=blur_face,
        num_faces=1,
    )


def test_analysis_display_parsed_from_disk(isolated_scenarios_file):
    s = get_scenario("visa-test")
    assert s is not None
    assert s.analysis_display is not None
    assert s.analysis_display.mode == "approval_probability"
    assert s.analysis_display.success_probability_after_pct == 98.9


def test_analysis_display_default_mode_for_legacy_scenario(isolated_scenarios_file):
    s = get_scenario("dating-photo")
    assert s is not None
    assert s.analysis_display is None


def test_to_public_dict_exposes_analysis_display(isolated_scenarios_file):
    s = get_scenario("visa-test")
    assert s is not None
    public = s.to_public_dict()
    assert public["analysis_display"] == {
        "mode": "approval_probability",
        "success_probability_after_pct": 98.9,
        "label_key": "wizard.analysis.approvalProbability",
    }


def test_is_approval_probability_scenario_for_visa(isolated_scenarios_file):
    s = get_scenario("visa-test")
    assert is_approval_probability_scenario(s) is True


def test_is_approval_probability_scenario_for_document(isolated_scenarios_file):
    s = get_scenario("document-photo")
    assert is_approval_probability_scenario(s) is True


def test_is_approval_probability_scenario_false_for_dating(isolated_scenarios_file):
    s = get_scenario("dating-photo")
    assert is_approval_probability_scenario(s) is False


def test_is_approval_probability_scenario_falls_back_for_legacy_visa():
    fake = AnalysisDisplay(mode="score")  # noqa: F841 — not used; just import smoke.
    # When ``analysis_display`` is missing entirely, kind/slug fallback
    # decides. Build an in-memory scenario without going through the
    # registry to verify that branch.
    from src.models.enums import AnalysisMode
    from src.scenarios.models import Scenario as Sc

    s = Sc(slug="visa-edge", kind="visa", api_mode=AnalysisMode.CV, enabled=True)
    assert is_approval_probability_scenario(s) is True


def test_estimate_probability_within_band(isolated_scenarios_file):
    s = get_scenario("visa-test")
    pct = estimate_approval_probability(_report(0.18, 0), s)
    assert 40.0 <= pct <= 92.0


def test_estimate_probability_higher_for_better_face(isolated_scenarios_file):
    s = get_scenario("visa-test")
    bad = estimate_approval_probability(_report(0.05, soft_warns=2, blur_face=20.0), s)
    good = estimate_approval_probability(_report(0.22, soft_warns=0, blur_face=120.0), s)
    assert good > bad


def test_estimate_probability_clamped_to_92(isolated_scenarios_file):
    s = get_scenario("visa-test")
    pct = estimate_approval_probability(_report(0.45, soft_warns=0, blur_face=300.0), s)
    assert pct <= 92.0


def test_estimate_probability_clamped_to_40(isolated_scenarios_file):
    s = get_scenario("visa-test")
    pct = estimate_approval_probability(
        _report(0.02, soft_warns=10, blur_face=5.0), s
    )
    assert pct >= 40.0


def test_estimate_probability_strictly_lower_for_visa_than_document(isolated_scenarios_file):
    visa = get_scenario("visa-test")
    document = get_scenario("document-photo")
    assert visa is not None and document is not None
    rpt = _report(0.18, 0, 100.0)
    pct_visa = estimate_approval_probability(rpt, visa)
    pct_doc = estimate_approval_probability(rpt, document)
    # Visa scoring is intentionally stricter (-4) than document-photo.
    assert pct_visa < pct_doc
