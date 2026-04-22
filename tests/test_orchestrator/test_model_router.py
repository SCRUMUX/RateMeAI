"""Tests for ModelRouter."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.orchestrator.advanced.model_router import ModelRouter, ModelSpec


def _mock_provider(name="mock"):
    p = MagicMock()
    p.__class__.__name__ = name
    return p


def test_select_by_capability():
    p1 = _mock_provider("reve")
    p2 = _mock_provider("replicate")
    router = ModelRouter([
        ModelSpec("reve_remix", p1, capabilities={"remix", "edit"}, cost_per_call=0.02, quality_tier=1),
        ModelSpec("replicate_flux", p2, capabilities={"remix", "inpaint"}, cost_per_call=0.05, quality_tier=2),
    ])

    result = router.select("inpaint", remaining_budget=0.10)
    assert result is not None
    spec, params = result
    assert spec.name == "replicate_flux"


def test_select_edit_prefers_best_tier():
    p1 = _mock_provider("reve")
    p2 = _mock_provider("replicate")
    router = ModelRouter([
        ModelSpec("reve_remix", p1, capabilities={"remix", "edit"}, cost_per_call=0.02, quality_tier=1),
        ModelSpec("replicate_flux", p2, capabilities={"remix", "inpaint"}, cost_per_call=0.05, quality_tier=2),
    ])

    result = router.select("edit", remaining_budget=0.10)
    assert result is not None
    spec, params = result
    assert spec.name == "reve_remix"
    assert params.get("use_edit") is True


def test_select_returns_none_when_over_budget():
    p1 = _mock_provider("reve")
    router = ModelRouter([
        ModelSpec("reve_remix", p1, capabilities={"remix"}, cost_per_call=0.05, quality_tier=1),
    ])

    result = router.select("remix", remaining_budget=0.01)
    assert result is None


def test_fallback_to_remix_when_capability_missing():
    p1 = _mock_provider("reve")
    router = ModelRouter([
        ModelSpec("reve_remix", p1, capabilities={"remix"}, cost_per_call=0.02, quality_tier=1),
    ])

    result = router.select("inpaint", remaining_budget=0.10)
    assert result is not None
    spec, _ = result
    assert spec.name == "reve_remix"


def test_cheapest_cost():
    p1 = _mock_provider("a")
    p2 = _mock_provider("b")
    router = ModelRouter([
        ModelSpec("a", p1, cost_per_call=0.10, quality_tier=1),
        ModelSpec("b", p2, cost_per_call=0.02, quality_tier=2),
    ])
    assert router.cheapest_cost == 0.02


def test_empty_router():
    router = ModelRouter()
    assert router.cheapest_cost == 0.0
    assert router.select("remix", 1.0) is None
