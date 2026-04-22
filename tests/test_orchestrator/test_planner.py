"""Tests for PipelinePlanner."""
from __future__ import annotations

from unittest.mock import patch

from src.models.enums import AnalysisMode
from src.orchestrator.advanced.planner import PipelinePlanner


def _apply_planner_settings(mock_settings):
    mock_settings.identity_match_threshold = 7.0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.pipeline_budget_max_usd = 0.15
    mock_settings.photorealism_enabled = True
    mock_settings.photorealism_threshold = 0.5


@patch("src.orchestrator.advanced.planner.settings")
def test_dating_plan_has_steps(mock_settings):
    _apply_planner_settings(mock_settings)

    planner = PipelinePlanner()
    plan = planner.plan(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        task_id="t1",
    )
    assert plan is not None
    assert len(plan.steps) >= 3
    assert plan.intent == "dating:warm_outdoor"
    assert plan.cost_budget == 0.15

    step_names = [s.step for s in plan.steps]
    assert "background_edit" in step_names
    assert "expression_hint" in step_names


@patch("src.orchestrator.advanced.planner.settings")
def test_cv_plan_has_clothing_step(mock_settings):
    _apply_planner_settings(mock_settings)

    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.CV, style="corporate", task_id="t2")
    assert plan is not None
    step_names = [s.step for s in plan.steps]
    assert "clothing_edit" in step_names


@patch("src.orchestrator.advanced.planner.settings")
def test_social_plan_has_style_overall(mock_settings):
    _apply_planner_settings(mock_settings)

    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.SOCIAL, style="influencer", task_id="t3")
    assert plan is not None
    step_names = [s.step for s in plan.steps]
    assert "style_overall" in step_names


def test_rating_returns_none():
    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.RATING, style="", task_id="t4")
    assert plan is None


def test_emoji_returns_none():
    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.EMOJI, style="", task_id="t5")
    assert plan is None


@patch("src.orchestrator.advanced.planner.settings")
def test_plan_filters_steps_by_enhancement_level(mock_settings):
    _apply_planner_settings(mock_settings)

    planner = PipelinePlanner()
    plan = planner.plan(
        mode=AnalysisMode.DATING, style="", task_id="t6", enhancement_level=1,
    )
    assert plan is not None
    step_names = [s.step for s in plan.steps]
    assert "lighting_adjust" in step_names
    assert "skin_correction" in step_names
    assert "background_edit" not in step_names
    assert "expression_hint" not in step_names


@patch("src.orchestrator.advanced.planner.settings")
def test_plan_to_dict(mock_settings):
    _apply_planner_settings(mock_settings)

    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.DATING, style="cafe", task_id="t7")
    d = plan.to_dict()
    assert d["task_id"] == "t7"
    assert isinstance(d["steps"], list)
    assert len(d["steps"]) > 0
    assert "step" in d["steps"][0]


@patch("src.orchestrator.advanced.planner.settings")
def test_global_gates_use_config_thresholds(mock_settings):
    mock_settings.identity_match_threshold = 8.5
    mock_settings.aesthetic_threshold = 7.0
    mock_settings.artifact_threshold = 0.03
    mock_settings.pipeline_budget_max_usd = 0.20
    mock_settings.photorealism_enabled = True
    mock_settings.photorealism_threshold = 0.6

    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.CV, style="", task_id="t8")
    assert plan.global_gates["identity_match"] == 8.5
    assert plan.global_gates["aesthetic_score"] == 7.0
    assert plan.global_gates["artifact_ratio"] == 0.03
    assert plan.global_gates["photorealism"] == 0.6
    assert plan.cost_budget == 0.20


@patch("src.orchestrator.advanced.planner.settings")
def test_photorealism_gate_included_when_enabled(mock_settings):
    _apply_planner_settings(mock_settings)
    mock_settings.photorealism_enabled = True
    mock_settings.photorealism_threshold = 0.5

    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.DATING, style="", task_id="t9")
    assert "photorealism" in plan.global_gates
    assert plan.global_gates["photorealism"] == 0.5


@patch("src.orchestrator.advanced.planner.settings")
def test_photorealism_gate_excluded_when_disabled(mock_settings):
    _apply_planner_settings(mock_settings)
    mock_settings.photorealism_enabled = False

    planner = PipelinePlanner()
    plan = planner.plan(mode=AnalysisMode.DATING, style="", task_id="t10")
    assert "photorealism" not in plan.global_gates


@patch("src.orchestrator.advanced.planner.settings")
def test_planner_keeps_all_dating_steps_regardless_of_strengths(mock_settings):
    """Strengths-based step filtering was retired in PR1.4 — the planner is
    deterministic for a given (mode, enhancement_level) so that multi-pass
    execution is reproducible when it comes back online."""
    _apply_planner_settings(mock_settings)

    planner = PipelinePlanner()
    plan = planner.plan(
        mode=AnalysisMode.DATING, style="", task_id="t11",
        analysis_result={"strengths": ["Отличный фон и освещение"]},
    )
    step_names = [s.step for s in plan.steps]
    assert "background_edit" in step_names
    assert "lighting_adjust" in step_names
