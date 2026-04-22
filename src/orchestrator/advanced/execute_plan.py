"""Reserved: multi-pass plan execution.

Executes a :class:`~src.orchestrator.advanced.planner.PipelinePlan`
step-by-step with budget enforcement, intermediate storage, per-step
model routing and global quality-gate validation at the end. This is
the machinery behind advanced / premium scenarios (HD retouch,
compliance-loop for documents, N-variants) and is **not** invoked by
the current single-pass runtime.

See ``docs/architecture/reserved.md`` for activation conditions and the
roadmap towards Phase 2 (Scenario Engine) and Phase 3 (FLUX via FAL).
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from src.metrics import IDENTITY_SCORE, REVE_CALLS
from src.models.enums import AnalysisMode
from src.orchestrator.advanced.model_router import ModelRouter
from src.orchestrator.advanced.planner import PipelinePlan, PipelineStep
from src.orchestrator.errors import format_image_gen_error
from src.orchestrator.trace import trace_step as _trace_step
from src.prompts.engine import PromptEngine
from src.providers.base import StorageProvider
from src.services.postprocess import inject_exif_only

logger = logging.getLogger(__name__)


ProgressCallback = Callable[[str, int, int], Awaitable[None]]


class AdvancedPipelineExecutor:
    """Execute a multi-step :class:`PipelinePlan`.

    The constructor deliberately asks for every heavy collaborator up
    front so the single-pass :class:`ImageGenerationExecutor` can remain
    free of :class:`ModelRouter` and segmentation services.
    """

    def __init__(
        self,
        prompt_engine: PromptEngine,
        model_router: ModelRouter,
        storage: StorageProvider,
        gate_runner_getter: Callable,
        apply_local_postprocess: Callable[[bytes, AnalysisMode, str, float], bytes],
        compute_authenticity: Callable[[dict], float],
    ):
        self._prompt_engine = prompt_engine
        self._model_router = model_router
        self._storage = storage
        self._get_gate_runner = gate_runner_getter
        self._apply_local_postprocess = apply_local_postprocess
        self._compute_authenticity = compute_authenticity

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
        gender: str = "male",
        input_quality: Any | None = None,
    ) -> None:
        gate_runner = self._get_gate_runner()
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
                    gate_runner, remaining_budget, trace,
                    enhancement_level, gender=gender,
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
                    plan.global_gates, image_bytes, current_image,
                )
                result_dict["quality_report"] = quality_report
                trace["global_gates"] = [
                    {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value, "threshold": gr.threshold}
                    for gr in global_results
                ]

                auth_score = self._compute_authenticity(quality_report)
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

                try:
                    mp_face_area_ratio = (
                        float(getattr(input_quality, "face_area_ratio", 0.0) or 0.0)
                        if input_quality is not None else 0.0
                    )
                except (TypeError, ValueError):
                    mp_face_area_ratio = 0.0
                current_image = self._apply_local_postprocess(
                    current_image, mode, style or "", mp_face_area_ratio,
                )
                current_image = inject_exif_only(current_image)

                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, current_image)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url

                identity_match = quality_report.get("identity_match") or 0.0
                if identity_match:
                    IDENTITY_SCORE.observe(float(identity_match) / 10.0)
                result_dict["enhancement"] = {
                    "style": style or "default",
                    "mode": mode.value,
                    "provider": "multi_pass",
                    "identity_match": round(float(identity_match), 2) if identity_match else 0.0,
                    "steps_executed": len(intermediates),
                    "pipeline_type": "multi_pass",
                }
            else:
                logger.warning(
                    "Multi-pass produced no output for task=%s; not retrying image generation",
                    task_id,
                )
                trace["decisions"].append({
                    "phase": "execute_plan",
                    "decision": "No output after multi-pass",
                    "reason": "all steps failed or produced no output; no second provider pass allowed",
                })
                result_dict["image_gen_error"] = "empty_result"
                result_dict.setdefault("generation_warnings", []).append(
                    "Не удалось сгенерировать улучшенное фото. Попробуй загрузить другое фото или выбрать другой стиль."
                )

        except Exception as exc:
            logger.exception("Multi-pass pipeline failed for task=%s without fallback", task_id)
            err_text = format_image_gen_error(exc)
            trace["decisions"].append({
                "phase": "execute_plan",
                "decision": "Multi-pass failed",
                "reason": f"exception during multi-pass execution: {err_text}",
            })
            result_dict["image_gen_error"] = "generation_failed"
            result_dict["image_gen_error_message"] = err_text
            result_dict.setdefault("generation_warnings", []).append(
                "Произошла ошибка при генерации. Попробуй ещё раз или загрузи другое фото."
            )

    async def _run_single_step(
        self,
        step: PipelineStep,
        i: int,
        plan: PipelinePlan,
        mode: AnalysisMode,
        style: str,
        current_image: bytes,
        original_image: bytes,
        gate_runner,
        budget: float,
        trace: dict,
        enhancement_level: int = 0,
        gender: str = "male",
    ) -> tuple[bytes | None, float]:
        """Execute one pipeline step. Returns (output_bytes, cost_spent)."""
        with _trace_step(trace, f"step_{i}_{step.step}") as step_entry:
            prompt = self._prompt_engine.build_step_prompt(
                step.prompt_template, style, mode,
                enhancement_level=enhancement_level,
                gender=gender,
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

            # Reve REST rejects aspect_ratio / test_time_scaling /
            # postprocessing / mask_* on /v1/image/edit; only use_edit is
            # kept as an internal endpoint selector inside reve_provider
            # (stripped from the wire body by the whitelist builder).
            params: dict = {"use_edit": True}
            params.update(extra_params)

            raw = await model_spec.provider.generate(
                prompt, reference_image=current_image, params=dict(params),
            )
            REVE_CALLS.labels(
                mode=mode.value,
                step=step.step,
                provider=type(model_spec.provider).__name__,
            ).inc()
            if not raw or len(raw) <= 100:
                return None, model_spec.cost_per_call

            # Per-step identity gate is intentionally a *soft* check here:
            # an extra per-step VLM call doubles the cost of every
            # intermediate pass and ``run_global_gates`` at the end of
            # the plan already makes the binding identity check on the
            # final result.
            if step.gate.get("identity_match"):
                step_entry["gate"] = [{"gate": "identity_match", "deferred": "global"}]

            return raw, model_spec.cost_per_call


__all__ = ["AdvancedPipelineExecutor", "ProgressCallback"]
