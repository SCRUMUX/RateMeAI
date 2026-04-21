"""Tests for DeltaScorer — post-generation rescoring and top-level writeback.

These tests guard against regressions where DeltaScorer only populates the
`delta` / `perception_delta` structures but forgets to overwrite the flat
scalar score fields (`dating_score`, `social_score`, `score`, `trust`,
`competence`, `hireability`) and the `perception_scores` map. When those are
left at pre-generation values, the `/tasks/history` endpoint and the
personal-best gamification tracker silently keep the original baseline,
making the "improvement dynamics" invisible to the user in storage.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.enums import AnalysisMode
from src.orchestrator.executor import DeltaScorer


def _make_scorer(post_dict: dict) -> tuple[DeltaScorer, MagicMock]:
    storage = MagicMock()
    storage.download = AsyncMock(return_value=b"\xff\xd8\xff\xe0" + b"0" * 2048)

    service = MagicMock()
    result_mock = MagicMock()
    result_mock.model_dump = MagicMock(return_value=post_dict)
    service.analyze = AsyncMock(return_value=result_mock)

    router = MagicMock()
    router.get_service = MagicMock(return_value=service)

    scorer = DeltaScorer(router=router, storage=storage, redis=None)
    return scorer, service


@pytest.mark.asyncio
async def test_dating_writes_post_score_to_top_level():
    post_dict = {
        "dating_score": 8.5,
        "perception_scores": {"warmth": 7.2, "presence": 6.8, "appeal": 8.0},
    }
    scorer, _ = _make_scorer(post_dict)

    result_dict = {
        "dating_score": 6.0,
        "score": 6.0,
        "perception_scores": {"warmth": 5.0, "presence": 5.2, "appeal": 5.4},
        "quality_report": {"identity_match": 9.0, "photorealism_confidence": 0.9},
        "enhancement": {"style": "yacht"},
    }

    await scorer.compute(AnalysisMode.DATING, result_dict, user_id="u1", task_id="t1")

    delta = result_dict["delta"]["dating_score"]
    assert delta["pre"] == 6.0
    assert delta["post"] > delta["pre"]

    # Top-level flat fields must reflect the post value so `/tasks/history`
    # and any other flat-field consumer shows the improvement dynamics.
    assert result_dict["dating_score"] == delta["post"]
    assert result_dict["score"] == delta["post"]
    assert result_dict["score_after"] == delta["post"]
    assert result_dict["score_before"] == delta["pre"]


@pytest.mark.asyncio
async def test_social_writes_post_score_to_top_level():
    post_dict = {
        "social_score": 7.9,
        "perception_scores": {"warmth": 7.0, "presence": 7.1, "appeal": 7.3},
    }
    scorer, _ = _make_scorer(post_dict)

    result_dict = {
        "social_score": 5.5,
        "score": 5.5,
        "perception_scores": {"warmth": 5.0, "presence": 5.0, "appeal": 5.0},
        "quality_report": {"identity_match": 8.0, "photorealism_confidence": 0.9},
        "enhancement": {"style": "default"},
    }

    await scorer.compute(AnalysisMode.SOCIAL, result_dict, user_id="u1", task_id="t2")

    delta = result_dict["delta"]["social_score"]
    assert result_dict["social_score"] == delta["post"]
    assert result_dict["score"] == delta["post"]
    assert result_dict["score_after"] == delta["post"]
    assert result_dict["score_before"] == delta["pre"]


@pytest.mark.asyncio
async def test_cv_writes_all_three_post_scores_to_top_level():
    post_dict = {
        "trust": 8.2,
        "competence": 8.4,
        "hireability": 8.0,
        "perception_scores": {"warmth": 7.0, "presence": 7.5, "appeal": 7.2},
    }
    scorer, _ = _make_scorer(post_dict)

    result_dict = {
        "trust": 6.0,
        "competence": 6.1,
        "hireability": 6.2,
        "perception_scores": {"warmth": 5.0, "presence": 5.0, "appeal": 5.0},
        "quality_report": {"identity_match": 9.2, "photorealism_confidence": 0.95},
        "enhancement": {"style": "ceo"},
        "profession": "software engineer",
    }

    await scorer.compute(AnalysisMode.CV, result_dict, user_id="u1", task_id="t3")

    for key in ("trust", "competence", "hireability"):
        delta = result_dict["delta"][key]
        assert result_dict[key] == delta["post"], f"{key} must be post, got {result_dict[key]}"

    post_vals = [result_dict[k] for k in ("trust", "competence", "hireability")]
    expected_score_after = round(sum(post_vals) / len(post_vals), 2)
    assert result_dict["score_after"] == expected_score_after


@pytest.mark.asyncio
async def test_perception_scores_updated_with_post_values():
    """warmth/presence/appeal in perception_scores must be rewritten with
    post values so that `_persist_perception_scores` stores the real best."""
    post_dict = {
        "dating_score": 8.5,
        "perception_scores": {"warmth": 7.5, "presence": 7.2, "appeal": 7.8},
    }
    scorer, _ = _make_scorer(post_dict)

    result_dict = {
        "dating_score": 6.0,
        "perception_scores": {"warmth": 5.0, "presence": 5.1, "appeal": 5.2},
        "quality_report": {"identity_match": 9.0, "photorealism_confidence": 0.9},
        "enhancement": {"style": "yacht"},
    }

    await scorer.compute(AnalysisMode.DATING, result_dict, user_id="u1", task_id="t4")

    ps = result_dict["perception_scores"]
    for key in ("warmth", "presence", "appeal"):
        assert ps[key] == result_dict["perception_delta"][key]["post"], (
            f"perception_scores.{key} must equal perception_delta.{key}.post"
        )
        assert ps[key] > 5.2, (
            f"perception_scores.{key} must improve over pre baseline 5.x"
        )

    # Authenticity is always computed from the quality report and must land
    # in perception_scores alongside the other metrics.
    assert "authenticity" in ps
    assert ps["authenticity"] >= 5.0
