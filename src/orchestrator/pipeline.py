from __future__ import annotations

import asyncio
import io
import logging
import time
from contextlib import contextmanager

from src.config import settings
from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult
from src.orchestrator.merger import ResultMerger
from src.orchestrator.model_router import ModelRouter, build_model_registry
from src.orchestrator.planner import PipelinePlan, PipelinePlanner
from src.orchestrator.router import ModeRouter
from src.providers.base import ImageGenProvider, LLMProvider, StorageProvider
from src.prompts.engine import PromptEngine
from src.services.share import ShareCardGenerator
from src.utils.image import validate_and_normalize, has_face_heuristic
from src.utils.redis_keys import embedding_cache_key
from src.utils.security import extract_nsfw_from_analysis

logger = logging.getLogger(__name__)


@contextmanager
def _trace_step(trace: dict, step_name: str):
    """Context manager that records start/end timestamps and duration for a pipeline step."""
    entry: dict = {"started_at": time.time()}
    try:
        yield entry
    finally:
        entry["ended_at"] = time.time()
        entry["duration_ms"] = round((entry["ended_at"] - entry["started_at"]) * 1000, 1)
        trace["steps"][step_name] = entry


class AnalysisPipeline:
    def __init__(
        self,
        llm: LLMProvider,
        storage: StorageProvider,
        image_gen: ImageGenProvider | None = None,
        redis=None,
    ):
        self._llm = llm
        self._prompt_engine = PromptEngine()
        self._router = ModeRouter(llm, self._prompt_engine)
        self._share_gen = ShareCardGenerator(storage)
        self._merger = ResultMerger()
        self._storage = storage
        self._image_gen = image_gen
        self._redis = redis
        self._identity = None
        self._segmentation = None
        self._planner = PipelinePlanner()
        self._model_router: ModelRouter = build_model_registry(
            image_gen,
            cost_reve=settings.model_cost_reve,
            cost_replicate=settings.model_cost_replicate,
        )

    def _get_identity_service(self):
        if self._identity is None:
            try:
                from src.services.identity import IdentityService
                self._identity = IdentityService(threshold=settings.identity_threshold)
            except ImportError:
                logger.warning("InsightFace not installed — identity gate disabled")
        return self._identity

    def _get_segmentation_service(self):
        if self._segmentation is None:
            try:
                from src.services.segmentation import SegmentationService
                self._segmentation = SegmentationService()
            except ImportError:
                logger.warning("mediapipe not installed — segmentation disabled")
        return self._segmentation

    def _get_gate_runner(self):
        from src.services.quality_gates import QualityGateRunner
        return QualityGateRunner(identity_svc=self._get_identity_service(), llm=self._llm)

    async def _get_or_compute_embedding(self, task_id: str, image_bytes: bytes):
        """Return cached embedding from Redis, or compute and cache it."""
        import numpy as np

        identity_svc = self._get_identity_service()
        if identity_svc is None:
            return None

        if self._redis:
            try:
                cached = await self._redis.get(embedding_cache_key(task_id))
                if cached:
                    if isinstance(cached, str):
                        import base64
                        cached = base64.b64decode(cached)
                    return np.frombuffer(cached, dtype=np.float32).copy()
            except Exception:
                logger.debug("Embedding cache miss for task %s", task_id)

        emb = identity_svc.compute_embedding(image_bytes)
        if emb is not None and self._redis:
            try:
                import base64
                b64 = base64.b64encode(emb.astype(np.float32).tobytes()).decode()
                await self._redis.set(embedding_cache_key(task_id), b64, ex=3600)
            except Exception:
                logger.debug("Failed to cache embedding for task %s", task_id)

        return emb

    async def execute(
        self,
        mode: AnalysisMode,
        image_bytes: bytes,
        user_id: str,
        task_id: str,
        context: dict | None = None,
        progress_callback=None,
    ) -> dict:
        trace: dict = {
            "pipeline_started_at": time.time(),
            "steps": {},
            "decisions": [],
            "total_cost_usd": 0.0,
        }

        with _trace_step(trace, "preprocess"):
            image_bytes = await self._preprocess(image_bytes)

        with _trace_step(trace, "analyze"):
            result, result_dict = await self._analyze(mode, image_bytes, context)

        style = (context or {}).get("style", "")
        skip_gen = (context or {}).get("skip_image_gen", False)

        if skip_gen:
            result_dict["upgrade_prompt"] = True
        else:
            use_multipass = (
                settings.segmentation_enabled
                and mode in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL)
            )

            if use_multipass:
                plan = self._planner.plan(
                    mode=mode, style=style, task_id=task_id,
                    analysis_result=result_dict, has_face=True,
                )
            else:
                plan = None

            if plan and len(plan.steps) > 0:
                trace["decisions"].append({
                    "phase": "planning",
                    "decision": f"Multi-pass plan with {len(plan.steps)} steps",
                    "reason": f"mode={mode.value}, style={style or 'default'}, segmentation_enabled=True",
                })
                trace["plan"] = plan.to_dict()
                with _trace_step(trace, "execute_plan"):
                    await self._execute_plan(plan, mode, style, image_bytes, result_dict, user_id, task_id, trace, progress_callback)
            else:
                trace["decisions"].append({
                    "phase": "planning",
                    "decision": "Single-pass fallback",
                    "reason": "Multi-pass disabled or mode does not support it",
                })
                with _trace_step(trace, "generate_image"):
                    await self._generate_image(mode, style, image_bytes, result_dict, user_id, task_id, trace)

            if result_dict.get("generated_image_url") and mode in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL):
                with _trace_step(trace, "post_gen_rescore"):
                    await self._compute_delta(mode, image_bytes, result_dict, user_id, task_id)

        trace["pipeline_ended_at"] = time.time()
        trace["total_duration_ms"] = round((trace["pipeline_ended_at"] - trace["pipeline_started_at"]) * 1000, 1)
        result_dict["pipeline_trace"] = trace

        return await self._finalize(mode, result, result_dict, image_bytes, user_id, task_id)

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    async def _preprocess(self, image_bytes: bytes) -> bytes:
        image_bytes, _meta = validate_and_normalize(image_bytes)

        if not has_face_heuristic(image_bytes):
            raise ValueError("На фото не обнаружено лицо. Загрузи портретное фото.")

        return image_bytes

    # ------------------------------------------------------------------
    # Analysis (LLM scoring)
    # ------------------------------------------------------------------

    async def _analyze(self, mode: AnalysisMode, image_bytes: bytes, context: dict | None) -> tuple:
        service = self._router.get_service(mode)

        if mode == AnalysisMode.CV:
            profession = (context or {}).get("profession", "не указана")
            result = await service.analyze(image_bytes, profession=profession)
        else:
            result = await service.analyze(image_bytes)

        raw_dict = result if isinstance(result, dict) else (result.model_dump() if hasattr(result, "model_dump") else result)

        is_safe, reason = extract_nsfw_from_analysis(raw_dict)
        if not is_safe:
            raise ValueError(f"Фото не прошло модерацию: {reason}")

        if isinstance(result, RatingResult):
            result_dict = result.model_dump()
        else:
            result_dict = raw_dict

        return result, result_dict

    # ------------------------------------------------------------------
    # Multi-pass executor
    # ------------------------------------------------------------------

    async def _execute_plan(
        self,
        plan: PipelinePlan,
        mode: AnalysisMode,
        style: str,
        image_bytes: bytes,
        result_dict: dict,
        user_id: str,
        task_id: str,
        trace: dict,
        progress_callback=None,
    ) -> None:
        seg_svc = self._get_segmentation_service()
        gate_runner = self._get_gate_runner()

        original_embedding = await self._get_or_compute_embedding(task_id, image_bytes)
        current_image = image_bytes
        intermediates: list[str] = []
        remaining_budget = plan.cost_budget

        try:
            step_groups = self._group_parallel_steps(plan.steps)

            global_step_idx = 0
            for group in step_groups:
                if remaining_budget < self._model_router.cheapest_cost:
                    trace["decisions"].append({
                        "phase": f"step_{global_step_idx}",
                        "decision": "Skipped — budget exhausted",
                        "reason": f"remaining=${remaining_budget:.3f}",
                    })
                    break

                if len(group) == 1:
                    i = global_step_idx
                    step = group[0]
                    raw, cost = await self._run_single_step(
                        step, i, plan, mode, style, current_image, image_bytes,
                        original_embedding, seg_svc, gate_runner, remaining_budget, trace,
                    )
                    remaining_budget -= cost
                    trace["total_cost_usd"] = round(plan.cost_budget - remaining_budget, 4)

                    if progress_callback:
                        try:
                            await progress_callback(f"step_{i}_{step.step}", global_step_idx + 1, len(plan.steps))
                        except Exception:
                            pass

                    if raw and len(raw) > 100:
                        ikey = f"intermediate/{user_id}/{task_id}/step_{i}.jpg"
                        await self._storage.upload(ikey, raw)
                        intermediates.append(ikey)
                        current_image = raw
                    elif intermediates:
                        logger.warning("Step %s produced no output, keeping previous intermediate", step.step)

                    global_step_idx += 1
                else:
                    trace["decisions"].append({
                        "phase": f"parallel_group_{global_step_idx}",
                        "decision": f"Running {len(group)} steps in parallel",
                        "reason": ", ".join(s.step for s in group),
                    })

                    coros = []
                    for j, step in enumerate(group):
                        i = global_step_idx + j
                        coros.append(self._run_single_step(
                            step, i, plan, mode, style, current_image, image_bytes,
                            original_embedding, seg_svc, gate_runner, remaining_budget / len(group), trace,
                        ))

                    results_list = await asyncio.gather(*coros, return_exceptions=True)

                    for j, (step, res) in enumerate(zip(group, results_list)):
                        i = global_step_idx + j
                        if isinstance(res, Exception):
                            logger.warning("Parallel step %s failed: %s", step.step, res)
                            continue
                        raw, cost = res
                        remaining_budget -= cost
                        if raw and len(raw) > 100:
                            ikey = f"intermediate/{user_id}/{task_id}/step_{i}.jpg"
                            await self._storage.upload(ikey, raw)
                            intermediates.append(ikey)
                            current_image = raw

                    trace["total_cost_usd"] = round(plan.cost_budget - remaining_budget, 4)

                    if progress_callback:
                        try:
                            await progress_callback(
                                f"parallel_{global_step_idx}",
                                global_step_idx + len(group),
                                len(plan.steps),
                            )
                        except Exception:
                            pass

                    global_step_idx += len(group)

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
                        "Global quality gates failed for task=%s: %s",
                        task_id, quality_report.get("gates_failed"),
                    )
                    result_dict["image_gen_error"] = "quality_gates_failed"
                    return

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
                await self._generate_image(
                    mode, style, image_bytes, result_dict, user_id, task_id, trace,
                )

        except Exception:
            logger.exception("Multi-pass pipeline failed for task=%s, falling back to single-pass", task_id)
            trace["decisions"].append({
                "phase": "execute_plan",
                "decision": "Fallback to single-pass after multi-pass failure",
                "reason": "exception during multi-pass execution",
            })
            await self._generate_image(mode, style, image_bytes, result_dict, user_id, task_id, trace)

    # ------------------------------------------------------------------
    # Step execution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _group_parallel_steps(steps) -> list[list]:
        """Group consecutive steps with non-overlapping, non-full regions for parallel execution."""
        groups: list[list] = []
        current_group: list = []
        current_regions: set[str] = set()

        for step in steps:
            if step.region == "full" or step.region in current_regions:
                if current_group:
                    groups.append(current_group)
                current_group = [step]
                current_regions = {step.region}
            else:
                current_group.append(step)
                current_regions.add(step.region)

        if current_group:
            groups.append(current_group)

        return groups

    async def _run_single_step(
        self, step, i: int, plan, mode, style, current_image, original_image,
        original_embedding, seg_svc, gate_runner, budget, trace,
    ) -> tuple[bytes | None, float]:
        """Execute one pipeline step. Returns (output_bytes, cost_spent)."""
        with _trace_step(trace, f"step_{i}_{step.step}") as step_entry:
            prompt = self._prompt_engine.build_step_prompt(step.prompt_template, style, mode)

            mask_bytes = None
            if seg_svc and step.region != "full":
                masks = await seg_svc.segment(current_image)
                mask_img = masks.get(step.region)
                if mask_img:
                    buf = io.BytesIO()
                    mask_img.save(buf, format="PNG")
                    mask_bytes = buf.getvalue()

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

            params: dict = {"aspect_ratio": "auto", "test_time_scaling": 3}
            params.update(extra_params)
            if mask_bytes:
                params["mask_image"] = mask_bytes
                params["mask_region"] = step.region

            retry_limit = plan.retry_policy.get("max_retries", 1)
            raw = None

            for attempt in range(1, retry_limit + 2):
                raw = await model_spec.provider.generate(
                    prompt, reference_image=current_image, params=dict(params),
                )
                if not raw or len(raw) <= 100:
                    raw = None
                    continue

                gate_results = await gate_runner.run_gates(
                    step.gate, original_image, raw, original_embedding,
                )
                all_passed = all(gr.passed for gr in gate_results)
                step_entry[f"gate_attempt_{attempt}"] = [
                    {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value, "threshold": gr.threshold}
                    for gr in gate_results
                ]

                if all_passed:
                    break

                if attempt <= retry_limit:
                    logger.warning("Step %s attempt %d failed gates, retrying", step.step, attempt)
                    raw = None
                else:
                    logger.warning("Step %s exhausted retries, using last result", step.step)

            return raw, model_spec.cost_per_call

    # ------------------------------------------------------------------
    # Single-pass fallback (original logic)
    # ------------------------------------------------------------------

    async def _generate_image(
        self, mode: AnalysisMode, style: str, image_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str, trace: dict,
    ) -> None:
        if mode not in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING, AnalysisMode.SOCIAL):
            return
        if self._image_gen is None:
            return

        max_retries = settings.identity_max_retries
        identity_svc = self._get_identity_service()

        try:
            desc = str(result_dict.get("base_description", ""))
            prompt = self._prompt_engine.build_image_prompt(mode, style=style, base_description=desc)

            extra: dict = {}
            if mode in (AnalysisMode.CV, AnalysisMode.DATING, AnalysisMode.SOCIAL):
                extra = {"aspect_ratio": "auto", "test_time_scaling": 3}

            raw = None
            identity_score = 0.0
            attempt = 0

            for attempt in range(1, max_retries + 2):
                logger.info(
                    "Image generation attempt %d/%d mode=%s style=%s task=%s",
                    attempt, max_retries + 1, mode.value, style or "default", task_id,
                )
                with _trace_step(trace, f"image_gen_attempt_{attempt}"):
                    raw = await self._image_gen.generate(prompt, reference_image=image_bytes, params=extra or None)

                if not raw or len(raw) <= 100:
                    logger.warning("Image gen returned empty/tiny result (%s bytes)", len(raw) if raw else 0)
                    raw = None
                    continue

                if identity_svc and mode != AnalysisMode.EMOJI:
                    with _trace_step(trace, f"identity_gate_attempt_{attempt}") as gate_entry:
                        passed, identity_score = identity_svc.verify(image_bytes, raw)
                        gate_entry["similarity"] = round(identity_score, 3)
                        if identity_score == 0.0 and passed:
                            result_dict["identity_gate_skipped"] = True
                            gate_entry["skipped"] = True
                    if passed:
                        break
                    logger.warning(
                        "Identity gate failed: similarity=%.3f < threshold=%.2f (attempt %d)",
                        identity_score, settings.identity_threshold, attempt,
                    )
                    if attempt <= max_retries:
                        raw = None
                else:
                    break

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
                    "generation_attempts": attempt,
                    "pipeline_type": "single_pass",
                }
                result_dict["cost_breakdown"] = {
                    "steps": [{"step": "single_pass", "model": provider_name,
                               "cost_usd": estimated_cost * attempt}],
                    "total_usd": round(estimated_cost * attempt, 4),
                    "budget_usd": settings.pipeline_budget_max_usd,
                }
                logger.info("Image generated and stored: %s (identity=%.3f, attempts=%d)", gkey, identity_score, attempt)
            else:
                logger.warning("All image gen attempts failed for task=%s", task_id)
                result_dict["image_gen_error"] = "empty_result"
        except Exception:
            logger.exception("Image generation failed for mode %s", mode.value)
            result_dict["image_gen_error"] = "generation_failed"

    # ------------------------------------------------------------------
    # Delta scoring
    # ------------------------------------------------------------------

    async def _compute_delta(
        self, mode: AnalysisMode, original_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str,
    ) -> None:
        """Re-score the generated image and compute delta vs original analysis."""
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

            delta = {}
            if mode == AnalysisMode.DATING:
                pre = float(result_dict.get("dating_score", 0))
                post = float(post_dict.get("dating_score", 0))
                delta = {"dating_score": {"pre": pre, "post": post, "delta": round(post - pre, 1)}}
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    pre = float(result_dict.get(key, 0))
                    post = float(post_dict.get(key, 0))
                    delta[key] = {"pre": pre, "post": post, "delta": round(post - pre, 1)}
            elif mode == AnalysisMode.SOCIAL:
                pre = float(result_dict.get("social_score", 0))
                post = float(post_dict.get("social_score", 0))
                delta = {"social_score": {"pre": pre, "post": post, "delta": round(post - pre, 1)}}

            result_dict["delta"] = delta
            result_dict["post_score"] = post_dict
            logger.info("Delta computed for task=%s: %s", task_id, delta)
        except Exception:
            logger.exception("Post-gen re-scoring failed for task=%s", task_id)
            result_dict["delta_error"] = "rescoring_failed"

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    async def _finalize(
        self, mode: AnalysisMode, result, result_dict: dict,
        image_bytes: bytes, user_id: str, task_id: str,
    ) -> dict:
        share_card_url = None
        if mode == AnalysisMode.RATING and isinstance(result, RatingResult):
            try:
                share_card_url = await self._share_gen.generate_rating_card(
                    result=result,
                    photo_bytes=image_bytes,
                    user_id=user_id,
                    task_id=task_id,
                )
            except Exception:
                logger.exception("Failed to generate share card")

        return self._merger.merge(result_dict, share_card_url, user_id)
