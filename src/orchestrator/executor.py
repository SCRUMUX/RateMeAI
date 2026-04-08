"""ImageGenerationExecutor and DeltaScorer — extracted from AnalysisPipeline.

Handles multi-pass plan execution, single-pass fallback, and
post-generation delta scoring as standalone collaborators.
"""
from __future__ import annotations

import hashlib
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Awaitable

from src.config import settings
from src.metrics import REVE_CALLS, IDENTITY_SCORE
from src.models.enums import AnalysisMode
from src.orchestrator.model_router import ModelRouter
from src.orchestrator.planner import PipelinePlan
from src.prompts.engine import PromptEngine
from src.providers.base import ImageGenProvider, StorageProvider
from src.services.postprocess import composite_face_region, inject_exif_only
from src.services.prompt_ab import get_active_experiments, assign_variant, record_result

_LEVEL_TO_TTS: dict[int, int] = {
    1: 3,
    2: 4,
    3: 4,
    4: 5,
}

logger = logging.getLogger(__name__)


@contextmanager
def _trace_step(trace: dict, step_name: str):
    entry: dict = {"started_at": time.time()}
    try:
        yield entry
    finally:
        entry["ended_at"] = time.time()
        entry["duration_ms"] = round((entry["ended_at"] - entry["started_at"]) * 1000, 1)
        trace["steps"][step_name] = entry


ProgressCallback = Callable[[str, int, int], Awaitable[None]]


class ImageGenerationExecutor:
    """Runs image generation: multi-pass plans or single-pass fallback."""

    def __init__(
        self,
        image_gen: ImageGenProvider | None,
        prompt_engine: PromptEngine,
        model_router: ModelRouter,
        storage: StorageProvider,
        identity_svc_getter: Callable,
        gate_runner_getter: Callable,
        embedding_getter: Callable,
        segmentation_getter: Callable | None = None,
    ):
        self._image_gen = image_gen
        self._prompt_engine = prompt_engine
        self._model_router = model_router
        self._storage = storage
        self._get_identity_service = identity_svc_getter
        self._get_gate_runner = gate_runner_getter
        self._get_or_compute_embedding = embedding_getter
        self._get_segmentation = segmentation_getter

    async def _record_ab_metrics(self, task_id: str, quality_report: dict, redis=None) -> None:
        """Record quality metrics for any active A/B experiments."""
        for exp in get_active_experiments():
            variant = assign_variant(exp.experiment_id, task_id)
            if variant:
                metrics = {
                    "identity_score": float(quality_report.get("face_similarity") or 0),
                    "aesthetic_score": float(quality_report.get("aesthetic_score") or 0),
                    "niqe_score": float(quality_report.get("niqe_score") or 0),
                }
                await record_result(redis, exp.experiment_id, variant.name, metrics)

    async def execute_plan(
        self,
        plan: PipelinePlan,
        mode: AnalysisMode,
        style: str,
        image_bytes: bytes,
        result_dict: dict,
        user_id: str,
        task_id: str,
        trace: dict,
        enhancement_level: int = 0,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        gate_runner = self._get_gate_runner()
        original_embedding = await self._get_or_compute_embedding(task_id, image_bytes)
        current_image = image_bytes
        intermediates: list[str] = []
        remaining_budget = plan.cost_budget

        try:
            for i, step in enumerate(plan.steps):
                if remaining_budget < self._model_router.cheapest_cost:
                    trace["decisions"].append({
                        "phase": f"step_{i}",
                        "decision": "Skipped — budget exhausted",
                        "reason": f"remaining=${remaining_budget:.3f}",
                    })
                    break

                raw, cost = await self._run_single_step(
                    step, i, plan, mode, style, current_image, image_bytes,
                    original_embedding, gate_runner, remaining_budget, trace,
                    enhancement_level,
                )
                remaining_budget -= cost
                trace["total_cost_usd"] = round(plan.cost_budget - remaining_budget, 4)

                if progress_callback:
                    try:
                        await progress_callback(f"step_{i}_{step.step}", i + 1, len(plan.steps))
                    except Exception:
                        pass

                if raw and len(raw) > 100:
                    ikey = f"intermediate/{user_id}/{task_id}/step_{i}.jpg"
                    await self._storage.upload(ikey, raw)
                    intermediates.append(ikey)
                    current_image = raw
                elif intermediates:
                    logger.warning("Step %s produced no output, keeping previous intermediate", step.step)

            if current_image is not image_bytes and len(current_image) > 100:
                global_passed, global_results, quality_report = await gate_runner.run_global_gates(
                    plan.global_gates, image_bytes, current_image, original_embedding,
                )
                result_dict["quality_report"] = quality_report
                trace["global_gates"] = [
                    {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value, "threshold": gr.threshold}
                    for gr in global_results
                ]

                auth_score = _compute_authenticity(quality_report)
                ps = result_dict.get("perception_scores")
                if isinstance(ps, dict):
                    ps["authenticity"] = auth_score
                elif hasattr(ps, "authenticity"):
                    ps.authenticity = auth_score

                result_dict["cost_breakdown"] = {
                    "steps": [
                        {
                            "step": k,
                            "model": v.get("model", "unknown"),
                            "cost_usd": v.get("estimated_cost_usd", 0),
                        }
                        for k, v in trace["steps"].items()
                        if k.startswith("step_") and "model" in v
                    ],
                    "total_usd": trace["total_cost_usd"],
                    "budget_usd": plan.cost_budget,
                }

                if not global_passed:
                    logger.warning(
                        "Global quality gates failed for task=%s: %s — delivering with warning",
                        task_id, quality_report.get("gates_failed"),
                    )
                    result_dict["quality_warning"] = True

                await self._record_ab_metrics(task_id, quality_report)

                current_image = inject_exif_only(current_image)

                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, current_image)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url

                identity_score = quality_report.get("face_similarity") or 0.0
                result_dict["enhancement"] = {
                    "style": style or "default",
                    "mode": mode.value,
                    "provider": "multi_pass",
                    "identity_score": round(identity_score, 3) if identity_score else 0.0,
                    "steps_executed": len(intermediates),
                    "pipeline_type": "multi_pass",
                }
            else:
                logger.warning(
                    "Multi-pass produced no output for task=%s, falling back to single-pass",
                    task_id,
                )
                trace["decisions"].append({
                    "phase": "execute_plan",
                    "decision": "Fallback to single-pass after multi-pass produced no output",
                    "reason": "all steps failed or produced no output",
                })
                await self.single_pass(
                    mode, style, image_bytes, result_dict, user_id, task_id, trace,
                )

        except Exception:
            logger.exception("Multi-pass pipeline failed for task=%s, falling back to single-pass", task_id)
            trace["decisions"].append({
                "phase": "execute_plan",
                "decision": "Fallback to single-pass after multi-pass failure",
                "reason": "exception during multi-pass execution",
            })
            await self.single_pass(mode, style, image_bytes, result_dict, user_id, task_id, trace)

    async def _run_single_step(
        self, step, i: int, plan, mode, style, current_image, original_image,
        original_embedding, gate_runner, budget, trace, enhancement_level: int = 0,
    ) -> tuple[bytes | None, float]:
        """Execute one pipeline step. Returns (output_bytes, cost_spent)."""
        with _trace_step(trace, f"step_{i}_{step.step}") as step_entry:
            prompt = self._prompt_engine.build_step_prompt(
                step.prompt_template, style, mode,
                enhancement_level=enhancement_level,
            )

            selection = self._model_router.select(step.model_preference, budget)
            if selection is None:
                trace["decisions"].append({
                    "phase": f"step_{i}_{step.step}",
                    "decision": "Skipped — no model available within budget",
                    "reason": f"preference={step.model_preference}, budget=${budget:.3f}",
                })
                return None, 0.0

            model_spec, extra_params = selection
            step_entry["model"] = model_spec.name
            step_entry["estimated_cost_usd"] = model_spec.cost_per_call

            trace["decisions"].append({
                "phase": f"step_{i}_{step.step}",
                "decision": f"Selected {model_spec.name}",
                "reason": f"tier={model_spec.quality_tier}, cost=${model_spec.cost_per_call:.3f}, budget_left=${budget:.3f}",
            })

            tts = _LEVEL_TO_TTS.get(enhancement_level, settings.reve_test_time_scaling)
            params: dict = {
                "aspect_ratio": "auto",
                "test_time_scaling": tts,
                "use_edit": True,
                "postprocessing": [{"process": "upscale", "upscale_factor": 2}],
            }
            params.update(extra_params)
            if step.region != "full":
                params["mask_region"] = step.region
                if settings.segmentation_enabled and self._get_segmentation:
                    try:
                        seg_svc = self._get_segmentation()
                        if seg_svc:
                            masks = await seg_svc.segment(current_image)
                            region_mask = masks.get(step.region)
                            if region_mask is not None:
                                import io as _io
                                mask_buf = _io.BytesIO()
                                region_mask.save(mask_buf, format="PNG")
                                params["mask_image"] = mask_buf.getvalue()
                                step_entry["mask_provided"] = True
                    except Exception:
                        logger.debug("Segmentation mask failed for step %s, using text hint", step.step)

            raw = await model_spec.provider.generate(
                prompt, reference_image=current_image, params=dict(params),
            )
            REVE_CALLS.labels(mode=mode.value, step=step.step).inc()
            if not raw or len(raw) <= 100:
                return None, model_spec.cost_per_call

            if step.gate.get("face_similarity") and original_embedding is not None:
                gate_results = await gate_runner.run_gates(
                    {"face_similarity": step.gate["face_similarity"]},
                    original_image, raw, original_embedding,
                )
                step_entry["gate"] = [
                    {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value, "threshold": gr.threshold}
                    for gr in gate_results
                ]
                if not all(gr.passed for gr in gate_results):
                    logger.warning(
                        "Step %s identity gate failed — accepting result (no retries)",
                        step.step,
                    )

            return raw, model_spec.cost_per_call

    async def single_pass(
        self, mode: AnalysisMode, style: str, image_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str, trace: dict,
    ) -> None:
        if mode not in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING, AnalysisMode.SOCIAL):
            return
        if self._image_gen is None:
            return

        identity_svc = self._get_identity_service()

        try:
            desc = str(result_dict.get("base_description", ""))
            prompt = self._prompt_engine.build_image_prompt(mode, style=style, base_description=desc)

            extra: dict = {}
            if mode in (AnalysisMode.CV, AnalysisMode.DATING, AnalysisMode.SOCIAL):
                extra = {
                    "aspect_ratio": "auto",
                    "test_time_scaling": settings.reve_test_time_scaling,
                    "use_edit": True,
                    "postprocessing": [{"process": "upscale", "upscale_factor": 2}],
                }

            raw = None
            identity_score = 0.0

            logger.info(
                "Image generation (edit mode) mode=%s style=%s task=%s",
                mode.value, style or "default", task_id,
            )
            with _trace_step(trace, "image_gen"):
                raw = await self._image_gen.generate(prompt, reference_image=image_bytes, params=extra or None)
            REVE_CALLS.labels(mode=mode.value, step="single_pass").inc()

            if not raw or len(raw) <= 100:
                logger.warning("Image gen returned empty/tiny result (%s bytes)", len(raw) if raw else 0)
                raw = None

            warnings: list[str] = result_dict.setdefault("generation_warnings", [])

            if raw and mode != AnalysisMode.EMOJI and identity_svc:
                with _trace_step(trace, "identity_check") as gate_entry:
                    passed, identity_score = identity_svc.verify(image_bytes, raw)
                    gate_entry["similarity"] = round(identity_score, 3)
                    gate_entry["passed"] = passed
                IDENTITY_SCORE.observe(identity_score)

                if not passed and 0.3 <= identity_score < settings.identity_threshold:
                    with _trace_step(trace, "face_compositing") as comp_entry:
                        composited, new_score = await composite_face_region(
                            image_bytes, raw, identity_svc,
                        )
                        comp_entry["original_score"] = round(identity_score, 3)
                        comp_entry["composited_score"] = round(new_score, 3)
                    if new_score > identity_score:
                        logger.info(
                            "Face compositing improved identity: %.3f -> %.3f (task=%s)",
                            identity_score, new_score, task_id,
                        )
                        raw = composited
                        identity_score = new_score
                        passed = identity_score >= settings.identity_threshold

                if identity_score == 0.0:
                    warnings.append(
                        "На обработанном фото не распознано лицо. "
                        "Загрузи чёткое портретное фото анфас с хорошим освещением "
                        "для более точного результата."
                    )
                elif identity_score < 0.3:
                    warnings.append(
                        "Результат значительно отличается от оригинала. "
                        "Для лучшего сходства загрузи более качественное фото: "
                        "чёткое лицо, ровное освещение, фронтальный ракурс."
                    )
                elif identity_score < 0.5:
                    warnings.append(
                        "Результат может немного отличаться от оригинала. "
                        "Загрузи фото в более высоком качестве — чёткий портрет "
                        "анфас даст лучший результат."
                    )
                elif identity_score < 0.75:
                    warnings.append(
                        "Небольшие отличия от оригинала. "
                        "Для максимальной точности используй качественное фото "
                        "с чётким лицом крупным планом."
                    )

                logger.info(
                    "Identity gate: similarity=%.3f threshold=%.2f passed=%s warnings=%d (task=%s)",
                    identity_score, settings.identity_threshold, passed,
                    len(warnings), task_id,
                )

            if raw and len(raw) > 100 and mode != AnalysisMode.EMOJI:
                try:
                    gate_runner = self._get_gate_runner()
                    original_embedding = await self._get_or_compute_embedding(task_id, image_bytes)
                    sp_gates: dict[str, float] = {
                        "aesthetic_score": settings.aesthetic_threshold,
                    }
                    if settings.photorealism_enabled:
                        sp_gates["photorealism"] = settings.photorealism_threshold
                    sp_gates["niqe"] = 5.0

                    with _trace_step(trace, "single_pass_gates") as sp_entry:
                        sp_passed, sp_results, sp_report = await gate_runner.run_global_gates(
                            sp_gates, image_bytes, raw, original_embedding,
                        )
                        sp_entry["gates"] = [
                            {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value}
                            for gr in sp_results
                        ]
                    result_dict["quality_report"] = sp_report
                    if not sp_passed:
                        logger.warning(
                            "Single-pass quality gates failed for task=%s: %s",
                            task_id, sp_report.get("gates_failed"),
                        )
                        result_dict["quality_warning"] = True

                    await self._record_ab_metrics(task_id, sp_report)
                except Exception:
                    logger.warning("Single-pass quality gates error for task=%s, skipping", task_id, exc_info=True)

            if raw and len(raw) > 100:
                raw = inject_exif_only(raw)

                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, raw)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url

                provider_name = type(self._image_gen).__name__
                estimated_cost = settings.model_cost_reve
                if "replicate" in provider_name.lower():
                    estimated_cost = settings.model_cost_replicate

                result_dict["enhancement"] = {
                    "style": style or "default",
                    "mode": mode.value,
                    "provider": provider_name,
                    "identity_score": round(identity_score, 3),
                    "generation_attempts": 1,
                    "pipeline_type": "single_pass_edit",
                }
                result_dict["cost_breakdown"] = {
                    "steps": [{"step": "single_pass_edit", "model": provider_name,
                               "cost_usd": estimated_cost}],
                    "total_usd": round(estimated_cost, 4),
                    "budget_usd": settings.pipeline_budget_max_usd,
                }
                logger.info("Image generated (edit mode): %s (identity=%.3f)", gkey, identity_score)
            else:
                logger.warning("Image gen returned no usable result for task=%s", task_id)
                result_dict["image_gen_error"] = "empty_result"
                warnings.append(
                    "Не удалось сгенерировать улучшенное фото. "
                    "Попробуй загрузить другое фото или выбрать другой стиль."
                )
        except Exception:
            logger.exception("Image generation failed for mode %s", mode.value)
            result_dict["image_gen_error"] = "generation_failed"
            result_dict.setdefault("generation_warnings", []).append(
                "Произошла ошибка при генерации. Попробуй ещё раз или загрузи другое фото."
            )


_PHI = 1.618
_MAX_DELTA = round(1 / _PHI, 2)  # 0.62
_MIN_POSITIVE_DELTA = 0.03


def _golden_delta(raw_delta: float, seed: str = "") -> float:
    """Clamp delta to gamification-friendly range with seed-based variation.

    Always returns a positive delta (gamification guarantee).
    """
    h = int(hashlib.md5(seed.encode()).hexdigest()[:4], 16) if seed else 0
    variation = ((h % 25) - 12) / 100.0
    if raw_delta <= 0:
        return round(max(_MIN_POSITIVE_DELTA + abs(variation) * 0.5, _MIN_POSITIVE_DELTA), 2)
    cap = _MAX_DELTA + variation
    clamped = min(raw_delta, cap)
    return round(max(clamped, _MIN_POSITIVE_DELTA), 2)


def _build_delta_entry(pre: float, raw_post: float, seed: str = "") -> dict:
    """Build a single {pre, post, delta} entry with golden-clamped delta."""
    gd = _golden_delta(raw_post - pre, seed)
    post = round(pre + gd, 2)
    return {"pre": round(pre, 2), "post": post, "delta": gd}


def _compute_authenticity(quality_report: dict) -> float:
    """Derive authenticity score from quality gate results.

    Authenticity is a guarantee parameter (not a growth metric): it reflects
    how real and identity-preserving the generated photo is.
    """
    face_sim = float(quality_report.get("face_similarity") or 0.9)
    photorealism = float(quality_report.get("photorealism_confidence") or 0.8)
    is_real = quality_report.get("is_photorealistic", True)
    teeth_ok = quality_report.get("teeth_natural", True)
    expr_ok = not quality_report.get("expression_altered", False)
    naturalness = 1.0 if (teeth_ok and expr_ok) else 0.5

    if not is_real:
        photorealism *= 0.5

    raw = face_sim * 4.0 + photorealism * 3.0 + naturalness * 3.0
    return round(min(9.99, max(5.0, raw)), 2)


_SCORE_REDIS_KEY = "ratemeai:score:{}:{}"
_SCORE_TTL = 86400


class DeltaScorer:
    """Re-scores the generated image and computes before/after delta.

    Supports score progression: if a previous post score exists in Redis,
    it is used as the new pre baseline so scores accumulate across generations.
    """

    def __init__(self, router, storage: StorageProvider, redis=None):
        self._router = router
        self._storage = storage
        self._redis = redis

    async def _load_previous_scores(self, user_id: str, mode: AnalysisMode) -> dict | None:
        if not self._redis:
            return None
        try:
            import json as _json
            raw = await self._redis.get(_SCORE_REDIS_KEY.format(user_id, mode.value))
            if raw:
                return _json.loads(raw)
        except Exception:
            logger.debug("Failed to load previous scores for user=%s mode=%s", user_id, mode.value)
        return None

    async def _save_scores(self, user_id: str, mode: AnalysisMode, scores: dict) -> None:
        if not self._redis:
            return
        try:
            import json as _json
            await self._redis.set(
                _SCORE_REDIS_KEY.format(user_id, mode.value),
                _json.dumps(scores),
                ex=_SCORE_TTL,
            )
        except Exception:
            logger.debug("Failed to save scores for user=%s mode=%s", user_id, mode.value)

    async def compute(
        self, mode: AnalysisMode, original_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str,
    ) -> None:
        try:
            gen_key = f"generated/{user_id}/{task_id}.jpg"
            gen_bytes = await self._storage.download(gen_key)
            if not gen_bytes:
                return

            service = self._router.get_service(mode)
            if mode == AnalysisMode.CV:
                post_result = await service.analyze(gen_bytes, profession=result_dict.get("profession", "не указана"))
            else:
                post_result = await service.analyze(gen_bytes)

            post_dict = post_result.model_dump() if hasattr(post_result, "model_dump") else post_result

            from src.orchestrator.pipeline import _SCORE_FLOOR, _PERCEPTION_FLOOR

            def _floor_post(raw: float, floor: float = _SCORE_FLOOR) -> float:
                return max(float(raw), floor)

            prev = await self._load_previous_scores(user_id, mode)
            prev_scores = prev.get("scores", {}) if prev else {}
            prev_perception = prev.get("perception", {}) if prev else {}

            delta: dict[str, Any] = {}
            new_scores: dict[str, float] = {}

            if mode == AnalysisMode.DATING:
                pre = float(prev_scores.get("dating_score", 0)) or float(result_dict.get("dating_score", 0))
                raw_post = _floor_post(post_dict.get("dating_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:dating_score")
                delta = {"dating_score": entry}
                new_scores["dating_score"] = entry["post"]
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    pre = float(prev_scores.get(key, 0)) or float(result_dict.get(key, 0))
                    raw_post = _floor_post(post_dict.get(key, 0))
                    entry = _build_delta_entry(pre, raw_post, f"{task_id}:{key}")
                    delta[key] = entry
                    new_scores[key] = entry["post"]
            elif mode == AnalysisMode.SOCIAL:
                pre = float(prev_scores.get("social_score", 0)) or float(result_dict.get("social_score", 0))
                raw_post = _floor_post(post_dict.get("social_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:social_score")
                delta = {"social_score": entry}
                new_scores["social_score"] = entry["post"]

            result_dict["delta"] = delta

            pre_perception = result_dict.get("perception_scores", {})
            if hasattr(pre_perception, "model_dump"):
                pre_perception = pre_perception.model_dump()
            post_perception = post_dict.get("perception_scores", {})
            if hasattr(post_perception, "model_dump"):
                post_perception = post_perception.model_dump()

            perception_delta: dict[str, Any] = {}
            new_perception: dict[str, float] = {}
            for key in ("warmth", "presence", "appeal"):
                pre_val = float(prev_perception.get(key, 0)) or float(pre_perception.get(key, 5.0))
                raw_post_val = _floor_post(float(post_perception.get(key, 5.0)), floor=_PERCEPTION_FLOOR)
                entry = _build_delta_entry(pre_val, raw_post_val, f"{task_id}:p:{key}")
                perception_delta[key] = entry
                new_perception[key] = entry["post"]

            result_dict["perception_delta"] = perception_delta

            await self._save_scores(user_id, mode, {
                "scores": new_scores,
                "perception": new_perception,
            })

            quality_report = result_dict.get("quality_report", {})
            if quality_report:
                auth_score = _compute_authenticity(quality_report)
            else:
                auth_score = 9.0
            result_dict.setdefault("perception_scores", {})
            ps = result_dict["perception_scores"]
            if isinstance(ps, dict):
                ps["authenticity"] = auth_score
            elif hasattr(ps, "authenticity"):
                ps.authenticity = auth_score

            result_dict["post_score"] = post_dict
            logger.info("Delta computed for task=%s: %s perception: %s", task_id, delta, perception_delta)
        except Exception:
            logger.exception("Post-gen re-scoring failed for task=%s", task_id)
            result_dict["delta_error"] = "rescoring_failed"
