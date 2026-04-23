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
    llm.analyze_image = AsyncMock(
        side_effect=[
            {"score": 6.0, "label": "ok"},
            {"score": 8.0, "label": "great"},
            {"score": 7.0, "label": "fine"},
        ]
    )

    result = _run(consensus_analyze(llm, b"img", "prompt", temperature=0.0, n=3))
    assert result["score"] == 7.0
    assert llm.analyze_image.await_count == 3


def test_consensus_handles_partial_failure():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(
        side_effect=[
            {"score": 8.0},
            Exception("LLM error"),
            {"score": 6.0},
        ]
    )

    result = _run(consensus_analyze(llm, b"img", "prompt", n=3))
    assert result["score"] == 7.0


def test_consensus_all_fail_returns_empty():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=Exception("down"))

    result = _run(consensus_analyze(llm, b"img", "prompt", n=3))
    assert result == {}

def test_consensus_n1_fail_returns_empty():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=Exception("down"))

    result = _run(consensus_analyze(llm, b"img", "prompt", n=1))
    assert result == {}


def test_median_dict_lists_take_longest():
    result = _median_dict(
        [
            {"items": ["a"]},
            {"items": ["a", "b", "c"]},
            {"items": ["a", "b"]},
        ]
    )
    assert result["items"] == ["a", "b", "c"]


def test_median_dict_mixed_keys():
    result = _median_dict(
        [
            {"score": 5.0, "label": "low"},
            {"score": 9.0, "label": "high"},
        ]
    )
    assert result["score"] == 7.0
    assert result["label"] == "low"


def test_consensus_wall_clock_timeout(monkeypatch):
    """B6: if the fan-out exceeds the wall-clock cap, raise TimeoutError so
    the worker's retry loop can classify it as transient."""
    from src.utils import consensus as consensus_mod

    monkeypatch.setattr(consensus_mod, "_CONSENSUS_WALL_TIMEOUT_S", 0.05)

    async def _slow(*_a, **_kw):
        await asyncio.sleep(1.0)
        return {"score": 1.0}

    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=_slow)

    with pytest.raises(TimeoutError):
        _run(consensus_analyze(llm, b"img", "prompt", n=3))


def test_consensus_wall_clock_timeout_n1(monkeypatch):
    """Same wall-clock cap must apply when n=1.

    Without it a hung provider could hold the worker slot for the whole
    tenacity budget (~96s) and block the ARQ job_timeout.
    """
    from src.utils import consensus as consensus_mod

    monkeypatch.setattr(consensus_mod, "_CONSENSUS_WALL_TIMEOUT_S", 0.05)

    async def _slow(*_a, **_kw):
        await asyncio.sleep(1.0)
        return {"score": 1.0}

    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=_slow)

    with pytest.raises(TimeoutError):
        _run(consensus_analyze(llm, b"img", "prompt", n=1))
