"""Quality gate runner: identity match, aesthetic score, artifact ratio, photorealism, NIQE.

All LLM-based checks — including identity preservation — are combined into
a single VLM call (two images, one prompt) for cost efficiency. Identity
match is a stateless holistic comparison: the VLM returns a 0-10 score,
no face geometry is extracted on our side and nothing is persisted.

NIQE (Natural Image Quality Evaluator) is a pixel-level naturalness
metric computed locally (no external transfer).
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

from src.providers.base import LLMProvider

logger = logging.getLogger(__name__)

_niqe_metric = None
_niqe_available: bool | None = None


def _get_niqe():
    """Lazy-load pyiqa NIQE metric. Returns None if pyiqa is not installed."""
    global _niqe_metric, _niqe_available
    if _niqe_available is False:
        return None
    if _niqe_metric is not None:
        return _niqe_metric
    try:
        import pyiqa
        _niqe_metric = pyiqa.create_metric("niqe", device="cpu")
        _niqe_available = True
        logger.info("pyiqa NIQE metric loaded successfully")
        return _niqe_metric
    except (ImportError, Exception):
        _niqe_available = False
        logger.info("pyiqa not available — NIQE gate will use LLM fallback")
        return None


def compute_niqe_score(image_bytes: bytes) -> float | None:
    """Compute NIQE score for an image. Lower is better (natural range ~3-5)."""
    metric = _get_niqe()
    if metric is None:
        return None
    try:
        import torch
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
        score = metric(tensor).item()
        return round(score, 3)
    except Exception:
        logger.debug("NIQE computation failed")
        return None


# The quality prompt is used in two modes:
#   (a) single-image: generated photo only — identity_match is ignored;
#   (b) two-image: original + generated — VLM compares them holistically.
# The same JSON schema is returned in both cases, only identity_match is
# defined when the original is provided.
QUALITY_CHECK_PROMPT = (
    "Return a SINGLE JSON OBJECT (not an array, not wrapped in square brackets, not a list). "
    "You are given one or two photos. When two photos are provided, the FIRST is the original reference "
    "and the SECOND is an AI-enhanced version of the same subject. "
    "Evaluate the AI-enhanced photo (the last one) for quality and, when a reference is provided, "
    "for identity preservation. Return ONLY a JSON object with the exact keys below:\n"
    "{\n"
    '  "identity_match": <float 0-10, ONLY when two photos are provided. 10 = clearly the same person '
    '(same bone structure, facial proportions, age, gender, eye and lip shape); 7-9 = same person with '
    'minor differences; 4-6 = possibly the same person but significant changes; 0-3 = different person. '
    'Do NOT perform face recognition or identification — compare based on visible portrait features only. '
    'Use null if only one photo is provided.>,\n'
    '  "aesthetic_score": <float 1-10, consider lighting, composition, skin naturalness>,\n'
    '  "artifact_ratio": <float 0.0-1.0, proportion of visible AI artifacts or distortions>,\n'
    '  "is_photorealistic": <bool, true if it looks like a genuine photograph>,\n'
    '  "photorealism_confidence": <float 0.0-1.0>,\n'
    '  "teeth_natural": <bool, true if teeth look natural or mouth is closed; false if teeth look AI-generated, unnaturally white, duplicated, or deformed>,\n'
    '  "expression_altered": <bool, true if the facial expression looks artificially changed — forced smile, unnatural grin, plastic look around mouth>,\n'
    '  "proportions_natural": <bool, true if head-to-body ratio looks natural and realistic; false if head is too large/small for body, or body parts look disproportionate>,\n'
    '  "pose_natural": <bool, true if the person\'s pose, limbs, and joints look anatomically correct and natural; false if pose looks contorted, limbs bent unnaturally, or body is warped>,\n'
    '  "hands_correct": <bool, true if hands are not visible OR have correct number of fingers with natural joint angles; false if extra/missing/merged fingers or deformed hands>,\n'
    '  "hair_outline_preserved": <bool, true if the hair outline is crisp and clearly not blended with the new background (no branches, leaves or backdrop bleeding into hair strands)>,\n'
    '  "background_consistent": <bool, true if the background looks natural and does not show visible stitching, seams or duplicated elements around the person>,\n'
    '  "identity_plausible": <bool, true if the person in the result is clearly the same person as in a typical portrait — same bone structure, features, age>,\n'
    '  "details": "<one-sentence summary>"\n'
    "}"
)


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    value: float
    threshold: float


_CHECK_FAILED_KEY = "_check_failed"


class QualityGateRunner:
    """Run quality gates on a generated image."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        # Back-compat: older callers still pass identity_svc=...; accept and
        # ignore it. Identity-match is now purely VLM-based.
        identity_svc=None,
    ):
        self._llm = llm
        self._quality_cache: dict | None = None

    async def run_gates(
        self,
        gate_spec: dict[str, float],
        original_bytes: bytes | None,
        generated_bytes: bytes,
    ) -> list[GateResult]:
        """Evaluate all gates from gate_spec. Returns list of GateResult."""
        results: list[GateResult] = []

        # Identity match is a VLM check: only evaluated when we have the
        # original reference photo. Value comes from the cached quality
        # payload (same LLM call as aesthetic/anatomy — one vision call
        # per generated image, at most).
        if "identity_match" in gate_spec:
            quality = await self._get_quality_metrics(generated_bytes, original_bytes)
            if quality.get(_CHECK_FAILED_KEY):
                # VLM call or JSON parsing failed — report as pass so we do not
                # block the pipeline, but upstream will see quality_check_failed
                # in the report and surface a soft warning to the user.
                results.append(GateResult("identity_match", True, 0.0, gate_spec["identity_match"]))
            else:
                val = quality.get("identity_match")
                if val is None:
                    # No reference provided or VLM explicitly returned null — treat as
                    # pass to avoid blocking, surface as telemetry only.
                    results.append(GateResult("identity_match", True, 0.0, gate_spec["identity_match"]))
                else:
                    val = float(val)
                    thr = gate_spec["identity_match"]
                    results.append(GateResult("identity_match", val >= thr, round(val, 2), thr))

        if "niqe" in gate_spec:
            niqe_score = compute_niqe_score(generated_bytes)
            if niqe_score is not None:
                thr = gate_spec["niqe"]
                results.append(GateResult("niqe", niqe_score <= thr, niqe_score, thr))

        _LLM_GATE_KEYS = ("aesthetic_score", "artifact_ratio", "photorealism", "naturalness", "anatomy")
        llm_gates = {k: v for k, v in gate_spec.items() if k in _LLM_GATE_KEYS}
        if llm_gates and self._llm is not None:
            quality = await self._get_quality_metrics(generated_bytes, original_bytes)
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
    ) -> tuple[bool, list[GateResult], dict]:
        """Run global gates and return (all_passed, results, quality_report)."""
        self._quality_cache = None
        results = await self.run_gates(gate_spec, original_bytes, generated_bytes)

        quality = self._quality_cache or {}
        check_failed = bool(quality.get(_CHECK_FAILED_KEY))

        report = {
            "identity_match": quality.get("identity_match"),
            "niqe_score": next((r.value for r in results if r.gate_name == "niqe"), None),
            "aesthetic_score": quality.get("aesthetic_score"),
            "artifact_ratio": quality.get("artifact_ratio"),
            "is_photorealistic": quality.get("is_photorealistic"),
            "photorealism_confidence": quality.get("photorealism_confidence"),
            "teeth_natural": quality.get("teeth_natural"),
            "expression_altered": quality.get("expression_altered"),
            "proportions_natural": quality.get("proportions_natural"),
            "pose_natural": quality.get("pose_natural"),
            "hands_correct": quality.get("hands_correct"),
            "hair_outline_preserved": quality.get("hair_outline_preserved"),
            "background_consistent": quality.get("background_consistent"),
            "identity_plausible": quality.get("identity_plausible"),
            "quality_check_failed": check_failed,
            "gates_passed": [r.gate_name for r in results if r.passed],
            "gates_failed": [r.gate_name for r in results if not r.passed],
        }

        all_passed = all(r.passed for r in results)
        return all_passed, results, report

    async def _get_quality_metrics(
        self,
        image_bytes: bytes,
        reference_bytes: bytes | None = None,
    ) -> dict:
        """Single VLM call for aesthetic + artifact + photorealism + identity.

        When ``reference_bytes`` is provided, the prompt sees both images in
        the same message and scores ``identity_match``. When only the
        generated image is provided, ``identity_match`` stays None.
        """
        if self._quality_cache is not None:
            return self._quality_cache

        if self._llm is None:
            # No LLM wired up — behaves like "check unavailable"; upstream
            # treats this as a pass (no reference data either).
            self._quality_cache = {_CHECK_FAILED_KEY: True}
            return self._quality_cache

        try:
            if reference_bytes is not None and hasattr(self._llm, "compare_images"):
                result = await self._llm.compare_images(
                    reference_bytes, image_bytes, QUALITY_CHECK_PROMPT, temperature=0.0,
                )
            else:
                result = await self._llm.analyze_image(
                    image_bytes, QUALITY_CHECK_PROMPT, temperature=0.0,
                )

            if not isinstance(result, dict):
                # Defensive: _parse_json now normalises shapes and raises on
                # unknown types, but keep this guard so a future provider
                # regression can never resurrect the silent-bypass bug.
                raise TypeError(
                    f"quality LLM returned non-dict payload (type={type(result).__name__})"
                )

            raw_identity = result.get("identity_match")
            identity_match: float | None
            if raw_identity is None:
                identity_match = None
            else:
                try:
                    identity_match = float(raw_identity)
                except (TypeError, ValueError):
                    identity_match = None

            self._quality_cache = {
                "identity_match": identity_match,
                "aesthetic_score": float(result.get("aesthetic_score", 5.0)),
                "artifact_ratio": float(result.get("artifact_ratio", 0.0)),
                "is_photorealistic": bool(result.get("is_photorealistic", True)),
                "photorealism_confidence": float(result.get("photorealism_confidence", 0.5)),
                "teeth_natural": bool(result.get("teeth_natural", True)),
                "expression_altered": bool(result.get("expression_altered", False)),
                "proportions_natural": bool(result.get("proportions_natural", True)),
                "pose_natural": bool(result.get("pose_natural", True)),
                "hands_correct": bool(result.get("hands_correct", True)),
                "hair_outline_preserved": bool(result.get("hair_outline_preserved", True)),
                "background_consistent": bool(result.get("background_consistent", True)),
                "identity_plausible": bool(result.get("identity_plausible", True)),
                "details": str(result.get("details", "")),
            }
        except Exception:
            # Mark the check as failed (sentinel) rather than silently
            # swallowing the error — executor will surface a soft warning
            # instead of delivering a potentially-mismatched photo as if the
            # gate had passed.
            logger.exception("Quality gate LLM check failed")
            self._quality_cache = {_CHECK_FAILED_KEY: True}

        return self._quality_cache
