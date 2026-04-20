"""Tests for QualityGateRunner (VLM-based identity, no embeddings)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.services.quality_gates import QualityGateRunner


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _llm_returning(payload: dict) -> MagicMock:
    """Build an LLM mock that supports both compare_images and analyze_image."""
    llm = MagicMock()
    llm.compare_images = AsyncMock(return_value=payload)
    llm.analyze_image = AsyncMock(return_value=payload)
    return llm


def test_identity_match_gate_passes():
    llm = _llm_returning({
        "identity_match": 8.5,
        "aesthetic_score": 7.0,
        "artifact_ratio": 0.01,
        "is_photorealistic": True,
    })

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"identity_match": 7.0},
        original_bytes=b"orig",
        generated_bytes=b"gen",
    ))
    assert len(results) == 1
    assert results[0].gate_name == "identity_match"
    assert results[0].passed is True
    assert results[0].value == 8.5
    llm.compare_images.assert_awaited_once()
    llm.analyze_image.assert_not_awaited()


def test_identity_match_gate_fails():
    llm = _llm_returning({
        "identity_match": 4.0,
        "aesthetic_score": 6.0,
        "artifact_ratio": 0.05,
        "is_photorealistic": True,
    })

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"identity_match": 7.0},
        original_bytes=b"orig",
        generated_bytes=b"gen",
    ))
    assert results[0].passed is False
    assert results[0].value == 4.0


def test_identity_match_without_reference_is_pass_through():
    """When no reference image is provided, identity_match is not blocking."""
    llm = _llm_returning({"identity_match": None, "aesthetic_score": 7.0})

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"identity_match": 7.0},
        original_bytes=None,
        generated_bytes=b"gen",
    ))
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].value == 0.0


def test_aesthetic_gate_via_llm():
    llm = _llm_returning({
        "aesthetic_score": 8.0,
        "artifact_ratio": 0.01,
        "is_photorealistic": True,
        "photorealism_confidence": 0.95,
        "details": "clean photo",
    })

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"aesthetic_score": 6.0, "artifact_ratio": 0.05},
        original_bytes=None,
        generated_bytes=b"gen",
    ))
    assert len(results) == 2
    aesthetic = next(r for r in results if r.gate_name == "aesthetic_score")
    artifact = next(r for r in results if r.gate_name == "artifact_ratio")
    assert aesthetic.passed is True
    assert aesthetic.value == 8.0
    assert artifact.passed is True
    assert artifact.value == 0.01


def test_aesthetic_gate_fails_below_threshold():
    llm = _llm_returning({
        "aesthetic_score": 4.0,
        "artifact_ratio": 0.1,
        "is_photorealistic": False,
    })

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"aesthetic_score": 6.0, "artifact_ratio": 0.05},
        original_bytes=None,
        generated_bytes=b"gen",
    ))
    aesthetic = next(r for r in results if r.gate_name == "aesthetic_score")
    artifact = next(r for r in results if r.gate_name == "artifact_ratio")
    assert aesthetic.passed is False
    assert artifact.passed is False


def test_global_gates_return_report_with_identity_match():
    llm = _llm_returning({
        "identity_match": 9.2,
        "aesthetic_score": 7.5,
        "artifact_ratio": 0.02,
        "is_photorealistic": True,
        "photorealism_confidence": 0.9,
        "details": "good quality",
    })

    runner = QualityGateRunner(llm=llm)
    all_passed, results, report = _run(runner.run_global_gates(
        {"identity_match": 7.0, "aesthetic_score": 6.0, "artifact_ratio": 0.05},
        original_bytes=b"orig",
        generated_bytes=b"gen",
    ))
    assert all_passed is True
    assert report["identity_match"] == 9.2
    assert report["aesthetic_score"] == 7.5
    assert report["is_photorealistic"] is True
    assert "identity_match" in report["gates_passed"]


def test_no_llm_skips_identity_gate():
    """Without an LLM, identity_match gate can't run but does not crash."""
    runner = QualityGateRunner(llm=None)
    results = _run(runner.run_gates(
        {"identity_match": 7.0},
        original_bytes=b"orig",
        generated_bytes=b"gen",
    ))
    # No reference quality payload -> identity_match value is None -> pass-through.
    assert len(results) == 1
    assert results[0].passed is True


def test_llm_failure_uses_default_quality():
    """When LLM fails, quality cache is empty and defaults apply."""
    llm = MagicMock()
    llm.analyze_image = AsyncMock(side_effect=Exception("LLM down"))

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"aesthetic_score": 6.0},
        original_bytes=None,
        generated_bytes=b"gen",
    ))
    assert len(results) == 1
    assert results[0].gate_name == "aesthetic_score"
    assert results[0].value == 5.0


def test_photorealism_gate_passes():
    llm = _llm_returning({
        "aesthetic_score": 7.0,
        "artifact_ratio": 0.01,
        "is_photorealistic": True,
        "photorealism_confidence": 0.9,
        "details": "clean photo",
    })

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"photorealism": 0.5},
        original_bytes=None,
        generated_bytes=b"gen",
    ))
    assert len(results) == 1
    assert results[0].gate_name == "photorealism"
    assert results[0].passed is True
    assert results[0].value == 0.9


def test_photorealism_gate_fails():
    llm = _llm_returning({
        "aesthetic_score": 6.0,
        "artifact_ratio": 0.05,
        "is_photorealistic": False,
        "photorealism_confidence": 0.3,
        "details": "looks artificial",
    })

    runner = QualityGateRunner(llm=llm)
    results = _run(runner.run_gates(
        {"photorealism": 0.5},
        original_bytes=None,
        generated_bytes=b"gen",
    ))
    assert len(results) == 1
    assert results[0].gate_name == "photorealism"
    assert results[0].passed is False
    assert results[0].value == 0.0
