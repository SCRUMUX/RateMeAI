"""Tests for QualityGateRunner."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np

from src.services.quality_gates import QualityGateRunner


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_face_similarity_gate_passes():
    identity = MagicMock()
    identity.compute_embedding.return_value = np.ones(512)
    identity.compare.return_value = 0.95

    runner = QualityGateRunner(identity_svc=identity)
    results = _run(runner.run_gates(
        {"face_similarity": 0.85},
        original_bytes=b"orig",
        generated_bytes=b"gen",
        original_embedding=np.ones(512),
    ))
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].value == 0.95


def test_face_similarity_gate_fails():
    identity = MagicMock()
    identity.compute_embedding.return_value = np.ones(512)
    identity.compare.return_value = 0.70

    runner = QualityGateRunner(identity_svc=identity)
    results = _run(runner.run_gates(
        {"face_similarity": 0.85},
        original_bytes=b"orig",
        generated_bytes=b"gen",
        original_embedding=np.ones(512),
    ))
    assert results[0].passed is False
    assert results[0].value == 0.70


def test_aesthetic_gate_via_llm():
    llm = MagicMock()
    llm.analyze_image = AsyncMock(return_value={
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
    llm = MagicMock()
    llm.analyze_image = AsyncMock(return_value={
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


def test_global_gates_return_report():
    identity = MagicMock()
    identity.compute_embedding.return_value = np.ones(512)
    identity.compare.return_value = 0.92

    llm = MagicMock()
    llm.analyze_image = AsyncMock(return_value={
        "aesthetic_score": 7.5,
        "artifact_ratio": 0.02,
        "is_photorealistic": True,
        "photorealism_confidence": 0.9,
        "details": "good quality",
    })

    runner = QualityGateRunner(identity_svc=identity, llm=llm)
    all_passed, results, report = _run(runner.run_global_gates(
        {"face_similarity": 0.85, "aesthetic_score": 6.0, "artifact_ratio": 0.05},
        original_bytes=b"orig",
        generated_bytes=b"gen",
        original_embedding=np.ones(512),
    ))
    assert all_passed is True
    assert report["face_similarity"] == 0.92
    assert report["aesthetic_score"] == 7.5
    assert report["is_photorealistic"] is True
    assert "face_similarity" in report["gates_passed"]


def test_no_identity_svc_skips_face_gate():
    """Without identity_svc, face_similarity gate is not evaluated."""
    runner = QualityGateRunner(identity_svc=None, llm=None)
    results = _run(runner.run_gates(
        {"face_similarity": 0.85},
        original_bytes=b"orig",
        generated_bytes=b"gen",
    ))
    assert len(results) == 0


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
    """Photorealism gate passes when image is photorealistic with high confidence."""
    llm = MagicMock()
    llm.analyze_image = AsyncMock(return_value={
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
    """Photorealism gate fails when image is not photorealistic."""
    llm = MagicMock()
    llm.analyze_image = AsyncMock(return_value={
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
