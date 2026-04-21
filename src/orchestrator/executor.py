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
from src.services.postprocess import (
    crop_to_aspect,
    inject_exif_only,
    upscale_lanczos,
)
# TODO: A/B framework — uncomment when experiments are registered via register_experiment()
# from src.services.prompt_ab import get_active_experiments, assign_variant, record_result

# Target aspect ratio for CV document styles. Applied *locally* after
# generation via PIL (see src.services.postprocess.crop_to_aspect) —
# Reve's /v1/image/edit endpoint does not accept aspect_ratio.
_CV_DOCUMENT_ASPECT: dict[str, str] = {
    "photo_3x4": "3:4",        # 30×40 мм
    "passport_rf": "3:4",      # 35×45 мм ≈ 3:4
    "visa_eu": "3:4",          # 35×45 мм ≈ 3:4
    "visa_schengen": "3:4",    # 35×45 мм
    "visa_us": "1:1",          # 50×50 мм
    "photo_4x6": "2:3",        # 40×60 мм
    "driver_license": "3:4",
}


def _document_target_aspect(style: str) -> str | None:
    """Return the local-crop target AR for a CV document style, else None."""
    return _CV_DOCUMENT_ASPECT.get((style or "").strip())


# Face-area threshold above which we locally LANCZOS-upscale the
# generated image x2 (bigger faces benefit from extra detail; smaller
# faces just amplify upscaling artefacts).
_UPSCALE_FACE_THRESHOLD = 0.15


def _apply_local_postprocess(
    raw: bytes, mode: AnalysisMode, style: str, face_area_ratio: float,
) -> bytes:
    """Apply local PIL post-processing (AR crop for documents, LANCZOS x2 for large faces).

    This replaces the previous Reve ``postprocessing=[{upscale}]`` and
    ``aspect_ratio`` fields that the Reve REST API does not accept.
    Silent-safe: any PIL failure returns the original bytes.
    """
    if not raw or len(raw) <= 100:
        return raw

    if mode == AnalysisMode.CV:
        target_ar = _document_target_aspect(style)
        if target_ar:
            try:
                raw = crop_to_aspect(raw, target_ar)
            except Exception:
                logger.debug("crop_to_aspect failed, using original", exc_info=True)

    if face_area_ratio and face_area_ratio >= _UPSCALE_FACE_THRESHOLD:
        try:
            raw = upscale_lanczos(raw, factor=2)
        except Exception:
            logger.debug("upscale_lanczos failed, using original", exc_info=True)

    return raw

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


def _format_image_gen_error(exc: BaseException) -> str:
    """Compact, UI-safe description of an image-generation failure.

    When multi-pass / single-pass catches an exception, we set
    ``image_gen_error="generation_failed"`` and the worker marks the task
    as ``completed`` with ``no_image_reason="generation_error"``. The web
    UI then picks a hard-coded "Попробуйте другой стиль" string and the
    real provider cause (e.g. Reve INVALID_PARAMETER_VALUE / rsid-...) is
    lost. Store a short diagnostic here so the frontend can surface it
    instead of the generic message.
    """
    exc_type = type(exc).__name__
    msg = str(exc) or exc_type
    parts: list[str] = []
    try:
        from src.providers.image_gen.reve_provider import ReveAPIError
        real: BaseException = exc
        for _ in range(5):
            if isinstance(real, ReveAPIError):
                break
            cause = getattr(real, "__cause__", None) or getattr(real, "__context__", None)
            if cause is None or cause is real:
                break
            real = cause
        if isinstance(real, ReveAPIError):
            if getattr(real, "status_code", None) is not None:
                parts.append(f"http={real.status_code}")
            if getattr(real, "error_code", None):
                parts.append(f"code={real.error_code}")
            if getattr(real, "request_id", None):
                parts.append(f"req={real.request_id}")
            msg = str(real) or msg
            exc_type = type(real).__name__
    except Exception:
        pass
    extras = (" " + " ".join(parts)) if parts else ""
    text = f"{exc_type}: {msg[:220]}{extras}"
    return text[:320]


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
        segmentation_getter: Callable | None = None,
    ):
        self._image_gen = image_gen
        self._prompt_engine = prompt_engine
        self._model_router = model_router
        self._storage = storage
        self._get_identity_service = identity_svc_getter
        self._get_gate_runner = gate_runner_getter
        self._get_segmentation = segmentation_getter

    # TODO: A/B framework — uncomment when experiments are registered via register_experiment()
    # async def _record_ab_metrics(self, task_id: str, quality_report: dict, redis=None) -> None:
    #     """Record quality metrics for any active A/B experiments."""
    #     for exp in get_active_experiments():
    #         variant = assign_variant(exp.experiment_id, task_id)
    #         if variant:
    #             metrics = {
    #                 "identity_match": float(quality_report.get("identity_match") or 0),
    #                 "aesthetic_score": float(quality_report.get("aesthetic_score") or 0),
    #                 "niqe_score": float(quality_report.get("niqe_score") or 0),
    #             }
    #             await record_result(redis, exp.experiment_id, variant.name, metrics)

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

                # await self._record_ab_metrics(task_id, quality_report)

                try:
                    mp_face_area_ratio = (
                        float(getattr(input_quality, "face_area_ratio", 0.0) or 0.0)
                        if input_quality is not None else 0.0
                    )
                except (TypeError, ValueError):
                    mp_face_area_ratio = 0.0
                current_image = _apply_local_postprocess(
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
            err_text = _format_image_gen_error(exc)
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
        self, step, i: int, plan, mode, style, current_image, original_image,
        gate_runner, budget, trace, enhancement_level: int = 0,
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

            # Per-step identity gate is intentionally a *soft* check here: an
            # extra per-step VLM call doubles the cost of every intermediate
            # pass and `run_global_gates` at the end of the plan already makes
            # the binding identity check on the final result. We therefore
            # skip per-step VLM calls and rely on the global gate only.
            if step.gate.get("identity_match"):
                step_entry["gate"] = [{"gate": "identity_match", "deferred": "global"}]

            return raw, model_spec.cost_per_call

    async def single_pass(
        self, mode: AnalysisMode, style: str, image_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str, trace: dict,
        gender: str = "male",
        input_quality: Any | None = None,
    ) -> None:
        if mode not in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING, AnalysisMode.SOCIAL):
            return
        if self._image_gen is None:
            return

        try:
            desc = str(result_dict.get("base_description", ""))
            input_hints = input_quality.to_prompt_hints() if input_quality is not None else None
            prompt = self._prompt_engine.build_image_prompt(
                mode, style=style, base_description=desc, gender=gender,
                input_hints=input_hints,
            )

            # Face area ratio drives two decisions:
            #   - whether to upscale x2 (bad idea for tiny faces, amplifies artefacts)
            #   - how strict HAIR protection should be
            face_area_ratio = (
                float(getattr(input_quality, "face_area_ratio", 0.0) or 0.0)
                if input_quality is not None else 0.0
            )

            # Reve REST /v1/image/edit accepts only
            # {edit_instruction, reference_image, version}. All prior
            # "richer" fields (aspect_ratio, test_time_scaling,
            # postprocessing, mask_image, mask_region) triggered
            # INVALID_PARAMETER_VALUE. AR for document photos and the
            # x2 upscale are applied locally after generate() — see
            # _apply_local_postprocess. `use_edit` is an internal flag
            # only: the reve_provider uses it to pick the edit vs remix
            # endpoint and never puts it on the wire.
            extra: dict = {"use_edit": True}

            raw = None
            identity_match: float = 0.0

            will_upscale = bool(
                mode in (AnalysisMode.CV, AnalysisMode.DATING, AnalysisMode.SOCIAL)
                and face_area_ratio >= _UPSCALE_FACE_THRESHOLD
            )
            doc_ar = _document_target_aspect(style) if mode == AnalysisMode.CV else None
            logger.info(
                "Image generation (edit mode) mode=%s style=%s task=%s local_upscale=%s local_crop_ar=%s",
                mode.value, style or "default", task_id,
                "x2" if will_upscale else "no",
                doc_ar or "none",
            )
            with _trace_step(trace, "image_gen"):
                raw = await self._image_gen.generate(prompt, reference_image=image_bytes, params=extra or None)

            if raw and len(raw) > 100:
                raw = _apply_local_postprocess(raw, mode, style, face_area_ratio)
            provider_name = type(self._image_gen).__name__
            REVE_CALLS.labels(
                mode=mode.value,
                step="single_pass",
                provider=provider_name,
            ).inc()

            if not raw or len(raw) <= 100:
                logger.warning("Image gen returned empty/tiny result (%s bytes)", len(raw) if raw else 0)
                raw = None

            warnings: list[str] = result_dict.setdefault("generation_warnings", [])

            if raw and len(raw) > 100 and mode != AnalysisMode.EMOJI:
                try:
                    gate_runner = self._get_gate_runner()
                    sp_gates: dict[str, float] = {
                        "identity_match": settings.identity_match_threshold,
                        "aesthetic_score": settings.aesthetic_threshold,
                    }
                    if settings.photorealism_enabled:
                        sp_gates["photorealism"] = settings.photorealism_threshold
                    sp_gates["niqe"] = 5.0

                    with _trace_step(trace, "single_pass_gates") as sp_entry:
                        sp_passed, sp_results, sp_report = await gate_runner.run_global_gates(
                            sp_gates, image_bytes, raw,
                        )
                        sp_entry["gates"] = [
                            {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value}
                            for gr in sp_results
                        ]
                    result_dict["quality_report"] = sp_report

                    identity_match = float(sp_report.get("identity_match") or 0.0)
                    if identity_match:
                        IDENTITY_SCORE.observe(identity_match / 10.0)

                    # Soft, user-facing warnings when identity preservation
                    # drops — mirrors the previous ArcFace-based UX messaging,
                    # but with the new 0-10 identity_match scale.
                    if identity_match == 0.0 and not sp_report.get("identity_match"):
                        # VLM returned null (not a failure, just no comparison)
                        pass
                    elif identity_match < settings.identity_match_soft_threshold:
                        warnings.append(
                            "Сильное отличие от оригинала — рекомендуем другое фото. "
                            "Лучше всего работает чёткое лицо крупным планом, анфас, "
                            "без затемнений и без сложного фона."
                        )
                    elif identity_match < settings.identity_match_threshold:
                        warnings.append(
                            "Результат может заметно отличаться от оригинала. "
                            "Для лучшего сходства загрузи фото в более высоком качестве."
                        )

                    if not sp_passed:
                        logger.warning(
                            "Single-pass quality gates failed for task=%s: %s",
                            task_id, sp_report.get("gates_failed"),
                        )
                        result_dict["quality_warning"] = True

                    # Actionable warnings from LLM quality check — surfaced as
                    # soft notices (we deliver the photo anyway per policy).
                    if sp_report.get("hair_outline_preserved") is False:
                        warnings.append(
                            "Контур волос на итоговом фото отличается от оригинала. "
                            "Для лучшего результата снимите фото на простом однотонном фоне."
                        )
                    if sp_report.get("background_consistent") is False:
                        warnings.append(
                            "На фото заметны артефакты стыка с фоном. "
                            "Попробуйте фото с чистым ровным фоном без сложных деталей."
                        )
                    if sp_report.get("hands_correct") is False:
                        warnings.append(
                            "На фото могут быть неточности в изображении рук. "
                            "Попробуйте снимок, где руки не видны или сложены спокойно."
                        )
                    if sp_report.get("pose_natural") is False:
                        warnings.append(
                            "Поза на итоговом фото выглядит не совсем естественно. "
                            "Лучше всего работает прямая осанка и симметричный кадр."
                        )

                    # await self._record_ab_metrics(task_id, sp_report)
                except Exception:
                    logger.warning("Single-pass quality gates error for task=%s, skipping", task_id, exc_info=True)

            if raw and len(raw) > 100:
                raw = inject_exif_only(raw)

                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, raw)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url

                estimated_cost = settings.model_cost_reve
                if "replicate" in provider_name.lower():
                    estimated_cost = settings.model_cost_replicate

                result_dict["enhancement"] = {
                    "style": style or "default",
                    "mode": mode.value,
                    "provider": provider_name,
                    "identity_match": round(identity_match, 2),
                    "generation_attempts": 1,
                    "pipeline_type": "single_pass_edit",
                }
                result_dict["cost_breakdown"] = {
                    "steps": [{"step": "single_pass_edit", "model": provider_name,
                               "cost_usd": estimated_cost}],
                    "total_usd": round(estimated_cost, 4),
                    "budget_usd": settings.pipeline_budget_max_usd,
                }
                logger.info("Image generated (edit mode): %s (identity_match=%.2f)", gkey, identity_match)
            else:
                logger.warning("Image gen returned no usable result for task=%s", task_id)
                result_dict["image_gen_error"] = "empty_result"
                warnings.append(
                    "Не удалось сгенерировать улучшенное фото. "
                    "Попробуй загрузить другое фото или выбрать другой стиль."
                )
        except Exception as exc:
            logger.exception("Image generation failed for mode %s", mode.value)
            result_dict["image_gen_error"] = "generation_failed"
            result_dict["image_gen_error_message"] = _format_image_gen_error(exc)
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
    if post <= pre:
        post = round(pre + _MIN_POSITIVE_DELTA, 2)
        gd = round(post - pre, 2)
    return {"pre": round(pre, 2), "post": post, "delta": gd}


def _compute_authenticity(quality_report: dict) -> float:
    """Derive authenticity score from quality gate results.

    Authenticity is a guarantee parameter (not a growth metric): it reflects
    how real and identity-preserving the generated photo is.

    Inputs are purely stateless scalars produced by the VLM quality gate
    (no local face embeddings): ``identity_match`` on 0-10 scale is
    rescaled to 0-1, everything else is used as-is.
    """
    # identity_match is 0-10 (VLM scale); if absent (e.g. single-image
    # quality check without reference), fall back to a neutral 0.9 ≈ 9/10.
    id_match_raw = quality_report.get("identity_match")
    if id_match_raw is None:
        id_factor = 0.9
    else:
        id_factor = max(0.0, min(1.0, float(id_match_raw) / 10.0))

    photorealism = float(quality_report.get("photorealism_confidence") or 0.8)
    is_real = quality_report.get("is_photorealistic", True)
    teeth_ok = quality_report.get("teeth_natural", True)
    expr_ok = not quality_report.get("expression_altered", False)
    naturalness = 1.0 if (teeth_ok and expr_ok) else 0.5

    if not is_real:
        photorealism *= 0.5

    raw = id_factor * 4.0 + photorealism * 3.0 + naturalness * 3.0
    return round(min(9.99, max(5.0, raw)), 2)


_SCORE_REDIS_KEY = "ratemeai:score:{}:{}:{}"  # user_id:mode:style
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

    async def _load_previous_scores(
        self, user_id: str, mode: AnalysisMode, style: str = "default",
    ) -> dict | None:
        if not self._redis:
            return None
        try:
            import json as _json
            raw = await self._redis.get(_SCORE_REDIS_KEY.format(user_id, mode.value, style))
            if raw:
                return _json.loads(raw)
        except Exception:
            logger.debug("Failed to load previous scores for user=%s mode=%s style=%s", user_id, mode.value, style)
        return None

    async def _save_scores(
        self, user_id: str, mode: AnalysisMode, scores: dict, style: str = "default",
    ) -> None:
        if not self._redis:
            return
        try:
            import json as _json
            await self._redis.set(
                _SCORE_REDIS_KEY.format(user_id, mode.value, style),
                _json.dumps(scores),
                ex=_SCORE_TTL,
            )
        except Exception:
            logger.debug("Failed to save scores for user=%s mode=%s style=%s", user_id, mode.value, style)

    async def compute(
        self,
        mode: AnalysisMode,
        result_dict: dict,
        user_id: str,
        task_id: str,
    ) -> None:
        """Delta re-score the generated image.

        The original bytes are no longer needed here — pre-scores are taken
        from ``result_dict`` (populated by the primary LLM pass or cached
        pre-analysis), and authenticity is derived from the quality report
        that was already produced during the synchronous single-pass/
        multi-pass quality gate (stateless VLM check, no persisted
        biometric artefacts). This keeps the original image out of the
        worker's working set after preprocessing.
        """
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

            from src.utils.humanize import SCORE_FLOOR as _SCORE_FLOOR, PERCEPTION_FLOOR as _PERCEPTION_FLOOR

            def _floor_post(raw: float, floor: float = _SCORE_FLOOR) -> float:
                return max(float(raw), floor)

            style = result_dict.get("enhancement", {}).get("style", "default")
            prev = await self._load_previous_scores(user_id, mode, style)
            prev_scores = prev.get("scores", {}) if prev else {}
            prev_perception = prev.get("perception", {}) if prev else {}

            delta: dict[str, Any] = {}
            new_scores: dict[str, float] = {}

            if mode == AnalysisMode.DATING:
                pre = float(prev_scores.get("dating_score", 0)) or float(result_dict.get("dating_score", 0)) or float(result_dict.get("score", 0))
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
                pre = float(prev_scores.get("social_score", 0)) or float(result_dict.get("social_score", 0)) or float(result_dict.get("score", 0))
                raw_post = _floor_post(post_dict.get("social_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:social_score")
                delta = {"social_score": entry}
                new_scores["social_score"] = entry["post"]

            result_dict["delta"] = delta

            if mode == AnalysisMode.CV:
                pre_vals = [delta[k]["pre"] for k in ("trust", "competence", "hireability") if k in delta]
                result_dict["score_before"] = round(sum(pre_vals) / len(pre_vals), 2) if pre_vals else None
                post_vals = [delta[k]["post"] for k in ("trust", "competence", "hireability") if k in delta]
                result_dict["score_after"] = round(sum(post_vals) / len(post_vals), 2) if post_vals else None
            else:
                first_key = next(iter(delta), None)
                result_dict["score_before"] = delta[first_key]["pre"] if first_key else None
                result_dict["score_after"] = delta[first_key]["post"] if first_key else None

            # IMPORTANT: overwrite top-level scalar score fields with post-gen
            # values so that any downstream consumer that reads the flat
            # `dating_score` / `social_score` / `score` / CV metrics (e.g. the
            # `/tasks/history` endpoint) sees the improvement dynamics of the
            # generated photo, not the pre-generation baseline.
            if mode == AnalysisMode.DATING and "dating_score" in delta:
                result_dict["dating_score"] = delta["dating_score"]["post"]
                result_dict["score"] = delta["dating_score"]["post"]
            elif mode == AnalysisMode.SOCIAL and "social_score" in delta:
                result_dict["social_score"] = delta["social_score"]["post"]
                result_dict["score"] = delta["social_score"]["post"]
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    if key in delta:
                        result_dict[key] = delta[key]["post"]

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
            }, style)

            quality_report = result_dict.get("quality_report", {})
            if quality_report:
                auth_score = _compute_authenticity(quality_report)
            else:
                auth_score = 9.0

            # Update perception_scores in place so that personal-best tracking
            # (`_persist_perception_scores`) and any API consumer reading the
            # flat map see the post-generation values. We normalise to a dict
            # first — the analysis layer may have returned a pydantic model.
            ps = result_dict.get("perception_scores")
            if hasattr(ps, "model_dump"):
                ps = ps.model_dump()
            if not isinstance(ps, dict):
                ps = {}
            for key in ("warmth", "presence", "appeal"):
                if key in perception_delta:
                    ps[key] = perception_delta[key]["post"]
            ps["authenticity"] = auth_score
            result_dict["perception_scores"] = ps

            result_dict["post_score"] = post_dict
            logger.info("Delta computed for task=%s: %s perception: %s", task_id, delta, perception_delta)
        except Exception:
            logger.exception("Post-gen re-scoring failed for task=%s", task_id)
            result_dict["delta_error"] = "rescoring_failed"
