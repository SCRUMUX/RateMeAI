"""Tests for consensus scoring utility."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.utils.consensus import consensus_analyze, _median_dict


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_single_sample_returns_direct_result():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(return_value={"score": 7.0, "text": "good"})

    result = _run(consensus_analyze(llm, b"img", "prompt", temperature=0.0, n=1))
    assert result == {"score": 7.0, "text": "good"}
    llm.analyze_image.assert_awaited_once()


def test_consensus_takes_median_of_numeric():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=[
        {"score": 6.0, "label": "ok"},
        {"score": 8.0, "label": "great"},
        {"score": 7.0, "label": "fine"},
    ])

    result = _run(consensus_analyze(llm, b"img", "prompt", temperature=0.0, n=3))
    assert result["score"] == 7.0
    assert llm.analyze_image.await_count == 3


def test_consensus_handles_partial_failure():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=[
        {"score": 8.0},
        Exception("LLM error"),
        {"score": 6.0},
    ])

    result = _run(consensus_analyze(llm, b"img", "prompt", n=3))
    assert result["score"] == 7.0


def test_consensus_all_fail_raises():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=Exception("down"))

    with pytest.raises(RuntimeError, match="All consensus calls failed"):
        _run(consensus_analyze(llm, b"img", "prompt", n=3))


def test_median_dict_lists_take_longest():
    result = _median_dict([
        {"items": ["a"]},
        {"items": ["a", "b", "c"]},
        {"items": ["a", "b"]},
    ])
    assert result["items"] == ["a", "b", "c"]


def test_median_dict_mixed_keys():
    result = _median_dict([
        {"score": 5.0, "label": "low"},
        {"score": 9.0, "label": "high"},
    ])
    assert result["score"] == 7.0
    assert result["label"] == "low"
