"""Quality gate runner: face similarity, aesthetic score, artifact ratio, photorealism.

Aesthetic, artifact, and photorealism checks are combined into a single LLM call
for cost efficiency. Face similarity uses the existing IdentityService.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from src.providers.base import LLMProvider

logger = logging.getLogger(__name__)

QUALITY_CHECK_PROMPT = (
    "Analyze this AI-enhanced photo for quality. Return ONLY a JSON object:\n"
    "{\n"
    '  "aesthetic_score": <float 1-10, consider lighting, composition, skin naturalness>,\n'
    '  "artifact_ratio": <float 0.0-1.0, proportion of visible AI artifacts or distortions>,\n'
    '  "is_photorealistic": <bool, true if it looks like a genuine photograph>,\n'
    '  "photorealism_confidence": <float 0.0-1.0>,\n'
    '  "teeth_natural": <bool, true if teeth look natural or mouth is closed; false if teeth look AI-generated, unnaturally white, duplicated, or deformed>,\n'
    '  "expression_altered": <bool, true if the facial expression looks artificially changed — forced smile, unnatural grin, plastic look around mouth>,\n'
    '  "proportions_natural": <bool, true if head-to-body ratio looks natural and realistic; false if head is too large/small for body, or body parts look disproportionate>,\n'
    '  "pose_natural": <bool, true if the person\'s pose, limbs, and joints look anatomically correct and natural; false if pose looks contorted, limbs bent unnaturally, or body is warped>,\n'
    '  "hands_correct": <bool, true if hands are not visible OR have correct number of fingers with natural joint angles; false if extra/missing/merged fingers or deformed hands>,\n'
    '  "details": "<one-sentence summary>"\n'
    "}"
)


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    value: float
    threshold: float


class QualityGateRunner:
    """Run quality gates on a generated image."""

    def __init__(
        self,
        identity_svc=None,
        llm: LLMProvider | None = None,
    ):
        self._identity = identity_svc
        self._llm = llm
        self._quality_cache: dict | None = None

    async def run_gates(
        self,
        gate_spec: dict[str, float],
        original_bytes: bytes | None,
        generated_bytes: bytes,
        original_embedding: np.ndarray | None = None,
    ) -> list[GateResult]:
        """Evaluate all gates from gate_spec. Returns list of GateResult."""
        results: list[GateResult] = []

        if "face_similarity" in gate_spec and self._identity is not None:
            results.append(await self._check_face_similarity(
                gate_spec["face_similarity"], original_bytes, generated_bytes, original_embedding,
            ))

        _LLM_GATE_KEYS = ("aesthetic_score", "artifact_ratio", "photorealism", "naturalness", "anatomy")
        llm_gates = {k: v for k, v in gate_spec.items() if k in _LLM_GATE_KEYS}
        if llm_gates and self._llm is not None:
            quality = await self._get_quality_metrics(generated_bytes)
            if "aesthetic_score" in llm_gates:
                val = quality.get("aesthetic_score", 5.0)
                thr = llm_gates["aesthetic_score"]
                results.append(GateResult("aesthetic_score", val >= thr, val, thr))
            if "artifact_ratio" in llm_gates:
                val = quality.get("artifact_ratio", 0.0)
                thr = llm_gates["artifact_ratio"]
                results.append(GateResult("artifact_ratio", val <= thr, val, thr))
            if "photorealism" in llm_gates:
                is_real = quality.get("is_photorealistic", True)
                confidence = quality.get("photorealism_confidence", 0.5)
                thr = llm_gates["photorealism"]
                passed = is_real and confidence >= thr
                val = confidence if is_real else 0.0
                results.append(GateResult("photorealism", passed, val, thr))
            if "naturalness" in llm_gates:
                teeth_ok = quality.get("teeth_natural", True)
                expr_altered = quality.get("expression_altered", False)
                passed = teeth_ok and not expr_altered
                val = 1.0 if passed else 0.0
                results.append(GateResult("naturalness", passed, val, 1.0))
            if "anatomy" in llm_gates:
                proportions_ok = quality.get("proportions_natural", True)
                pose_ok = quality.get("pose_natural", True)
                hands_ok = quality.get("hands_correct", True)
                passed = proportions_ok and pose_ok and hands_ok
                val = 1.0 if passed else 0.0
                results.append(GateResult("anatomy", passed, val, 1.0))

        return results

    async def run_global_gates(
        self,
        gate_spec: dict[str, float],
        original_bytes: bytes,
        generated_bytes: bytes,
        original_embedding: np.ndarray | None = None,
    ) -> tuple[bool, list[GateResult], dict]:
        """Run global gates and return (all_passed, results, quality_report)."""
        self._quality_cache = None
        results = await self.run_gates(gate_spec, original_bytes, generated_bytes, original_embedding)

        quality = await self._get_quality_metrics(generated_bytes) if self._llm else {}

        report = {
            "face_similarity": next((r.value for r in results if r.gate_name == "face_similarity"), None),
            "aesthetic_score": quality.get("aesthetic_score"),
            "artifact_ratio": quality.get("artifact_ratio"),
            "is_photorealistic": quality.get("is_photorealistic"),
            "teeth_natural": quality.get("teeth_natural"),
            "expression_altered": quality.get("expression_altered"),
            "proportions_natural": quality.get("proportions_natural"),
            "pose_natural": quality.get("pose_natural"),
            "hands_correct": quality.get("hands_correct"),
            "gates_passed": [r.gate_name for r in results if r.passed],
            "gates_failed": [r.gate_name for r in results if not r.passed],
        }

        all_passed = all(r.passed for r in results)
        return all_passed, results, report

    async def _check_face_similarity(
        self,
        threshold: float,
        original_bytes: bytes | None,
        generated_bytes: bytes,
        original_embedding: np.ndarray | None,
    ) -> GateResult:
        if self._identity is None or original_bytes is None:
            return GateResult("face_similarity", True, 0.0, threshold)

        if original_embedding is not None:
            gen_emb = self._identity.compute_embedding(generated_bytes)
            if gen_emb is None:
                return GateResult("face_similarity", False, 0.0, threshold)
            sim = self._identity.compare(original_embedding, gen_emb)
        else:
            passed, sim = self._identity.verify(original_bytes, generated_bytes)
            if sim == 0.0 and passed:
                return GateResult("face_similarity", True, 0.0, threshold)

        return GateResult("face_similarity", sim >= threshold, round(sim, 3), threshold)

    async def _get_quality_metrics(self, image_bytes: bytes) -> dict:
        """Single LLM call for aesthetic + artifact + photorealism."""
        if self._quality_cache is not None:
            return self._quality_cache

        if self._llm is None:
            return {}

        try:
            result = await self._llm.analyze_image(
                image_bytes, QUALITY_CHECK_PROMPT, temperature=0.0,
            )
            self._quality_cache = {
                "aesthetic_score": float(result.get("aesthetic_score", 5.0)),
                "artifact_ratio": float(result.get("artifact_ratio", 0.0)),
                "is_photorealistic": bool(result.get("is_photorealistic", True)),
                "photorealism_confidence": float(result.get("photorealism_confidence", 0.5)),
                "teeth_natural": bool(result.get("teeth_natural", True)),
                "expression_altered": bool(result.get("expression_altered", False)),
                "proportions_natural": bool(result.get("proportions_natural", True)),
                "pose_natural": bool(result.get("pose_natural", True)),
                "hands_correct": bool(result.get("hands_correct", True)),
                "details": str(result.get("details", "")),
            }
        except Exception:
            logger.exception("Quality gate LLM check failed")
            self._quality_cache = {}

        return self._quality_cache
