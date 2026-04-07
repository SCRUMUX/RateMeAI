"""ImageGenerationExecutor and DeltaScorer — extracted from AnalysisPipeline.

Handles multi-pass plan execution, single-pass fallback, and
post-generation delta scoring as standalone collaborators.
"""
from __future__ import annotations

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
    ):
        self._image_gen = image_gen
        self._prompt_engine = prompt_engine
        self._model_router = model_router
        self._storage = storage
        self._get_identity_service = identity_svc_getter
        self._get_gate_runner = gate_runner_getter
        self._get_or_compute_embedding = embedding_getter

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

            params: dict = {
                "aspect_ratio": "auto",
                "test_time_scaling": settings.reve_test_time_scaling,
                "use_edit": True,
            }
            params.update(extra_params)
            if step.region != "full":
                params["mask_region"] = step.region

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

                if identity_score == 0.0:
                    warnings.append(
                        "На обработанном фото не распознано лицо. "
                        "Попробуй загрузить чёткое портретное фото анфас."
                    )
                elif identity_score < 0.3:
                    warnings.append(
                        "Результат значительно отличается от оригинала. "
                        "Загрузи фото с чётким лицом и хорошим освещением."
                    )
                elif identity_score < 0.5:
                    warnings.append(
                        "Результат может отличаться от оригинала. "
                        "Для лучшего сходства используй фото анфас с равномерным освещением."
                    )
                elif identity_score < 0.75:
                    warnings.append(
                        "Небольшие отличия от оригинала. "
                        "Попробуй другой стиль для лучшего результата."
                    )

                logger.info(
                    "Identity gate: similarity=%.3f threshold=%.2f passed=%s warnings=%d (task=%s)",
                    identity_score, settings.identity_threshold, passed,
                    len(warnings), task_id,
                )

            if raw and len(raw) > 100:
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


class DeltaScorer:
    """Re-scores the generated image and computes before/after delta."""

    def __init__(self, router, storage: StorageProvider):
        self._router = router
        self._storage = storage

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

            delta: dict[str, Any] = {}
            if mode == AnalysisMode.DATING:
                pre = float(result_dict.get("dating_score", 0))
                post = float(post_dict.get("dating_score", 0))
                delta = {"dating_score": {"pre": round(pre, 2), "post": round(post, 2), "delta": round(post - pre, 2)}}
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    pre = float(result_dict.get(key, 0))
                    post = float(post_dict.get(key, 0))
                    delta[key] = {"pre": round(pre, 2), "post": round(post, 2), "delta": round(post - pre, 2)}
            elif mode == AnalysisMode.SOCIAL:
                pre = float(result_dict.get("social_score", 0))
                post = float(post_dict.get("social_score", 0))
                delta = {"social_score": {"pre": round(pre, 2), "post": round(post, 2), "delta": round(post - pre, 2)}}

            result_dict["delta"] = delta
            result_dict["post_score"] = post_dict
            logger.info("Delta computed for task=%s: %s", task_id, delta)
        except Exception:
            logger.exception("Post-gen re-scoring failed for task=%s", task_id)
            result_dict["delta_error"] = "rescoring_failed"
