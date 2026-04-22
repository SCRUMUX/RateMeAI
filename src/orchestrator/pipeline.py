from __future__ import annotations

import asyncio
import logging
import time

from src.config import settings
from src.metrics import PIPELINE_DURATION, LLM_CALLS
from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult
from src.orchestrator.executor import ImageGenerationExecutor, DeltaScorer
from src.orchestrator.merger import ResultMerger
from src.orchestrator.router import ModeRouter
from src.orchestrator.trace import PipelineStageError, trace_step as _trace_step  # noqa: F401 — re-exported for back-compat with tests/workers
from src.providers.base import ImageGenProvider, LLMProvider, StorageProvider
from src.prompts.engine import PromptEngine
from src.services.share import ShareCardGenerator
from src.services.ai_transfer_guard import task_context_scope
from src.services.task_contract import (
    get_market_id,
    is_cache_allowed,
)
from src.utils.humanize import humanize_result_scores
from src.utils.image import validate_and_normalize
from src.services.input_quality import analyze_input_quality, InputQualityReport
from src.utils.redis_keys import preanalysis_cache_keys
from src.utils.security import extract_nsfw_from_analysis
from src.services.face_prerestore import prerestore_if_needed
from src.tracing import async_span

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(
        self,
        llm: LLMProvider,
        storage: StorageProvider,
        image_gen: ImageGenProvider | None = None,
        redis=None,
        db_sessionmaker=None,
    ):
        self._llm = llm
        self._prompt_engine = PromptEngine()
        self._router = ModeRouter(llm, self._prompt_engine)
        self._share_gen = ShareCardGenerator(storage)
        self._merger = ResultMerger()
        self._storage = storage
        self._image_gen = image_gen
        self._redis = redis
        self._db_sessionmaker = db_sessionmaker
        self._identity = None
        # Multi-pass planning / model routing / segmentation live in
        # ``src.orchestrator.advanced`` and are intentionally *not* wired
        # into this single-pass pipeline. See ``docs/architecture/reserved.md``.
        self._executor = ImageGenerationExecutor(
            image_gen=image_gen,
            prompt_engine=self._prompt_engine,
            storage=storage,
            identity_svc_getter=self._get_identity_service,
            gate_runner_getter=self._get_gate_runner,
        )
        self._delta_scorer = DeltaScorer(router=self._router, storage=storage, redis=redis)

    def _get_identity_service(self):
        """Return the (lightweight) face-presence detector, if available.

        No longer loads InsightFace / ArcFace — the returned service only
        exposes ``detect_face`` (MediaPipe) and ``face_bbox`` (for optional
        segmentation). Identity preservation is verified by the VLM quality
        gate on two images (see services/quality_gates.py).
        """
        if self._identity is None:
            try:
                from src.services.identity import IdentityService
                self._identity = IdentityService()
            except ImportError:
                logger.warning("MediaPipe not installed — face presence detection disabled")
        return self._identity

    @property
    def identity_available(self) -> bool:
        return self._get_identity_service() is not None

    def _get_gate_runner(self):
        from src.services.quality_gates import QualityGateRunner
        return QualityGateRunner(llm=self._llm)

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
        market_id = get_market_id(context, fallback=settings.resolved_market_id)
        async with async_span("pipeline.execute", {
            "pipeline.mode": mode.value,
            "pipeline.task_id": task_id,
            "pipeline.user_id": user_id,
            "pipeline.market_id": market_id,
        }):
          with task_context_scope(context):
            return await self._execute_inner(
                mode, image_bytes, user_id, task_id, context, progress_callback, trace,
            )

    async def _execute_inner(
        self,
        mode: AnalysisMode,
        image_bytes: bytes,
        user_id: str,
        task_id: str,
        context: dict | None,
        progress_callback,
        trace: dict,
    ) -> dict:

        with _trace_step(trace, "preprocess"):
            image_bytes, img_meta, input_quality = await self._preprocess(image_bytes)

        with _trace_step(trace, "analyze"):
            pre_id = (context or {}).get("pre_analysis_id")
            cached_pre = None
            if pre_id and self._redis:
                try:
                    import json as _json
                    for cache_key in preanalysis_cache_keys(
                        pre_id,
                        get_market_id(context, fallback=settings.resolved_market_id),
                    ):
                        raw = await self._redis.get(cache_key)
                        if raw:
                            cached_pre = _json.loads(raw)
                            break
                except Exception:
                    logger.warning("Failed to load cached pre-analysis %s, falling back to LLM", pre_id)

            if cached_pre is not None:
                result = cached_pre
                result_dict = cached_pre
                trace["decisions"].append({
                    "phase": "analyze",
                    "decision": "Used cached pre-analysis",
                    "reason": f"pre_analysis_id={pre_id}",
                })
            else:
                result, result_dict = await self._analyze(mode, image_bytes, context)

        already_humanized = result_dict.get("_scores_humanized", False)
        if not already_humanized:
            humanize_result_scores(result_dict, task_id)

        warnings: list[str] = result_dict.setdefault("generation_warnings", [])
        # Surface soft warnings from input-quality gate as user-facing notices.
        # Hard resolution/blur issues are already blocked in _preprocess, so we
        # only translate actionable soft-warnings here.
        for w in input_quality.soft_warnings:
            warnings.append(f"{w.message} {w.suggestion}".strip())
        result_dict["input_quality"] = input_quality.to_public_dict()

        style = (context or {}).get("style", "")
        variant_id = (context or {}).get("variant_id", "")
        skip_gen = (context or {}).get("skip_image_gen", False)
        # TODO(gender-single-source): detected_gender is currently driven by the
        # LLM JSON output in four prompts (rating/dating/cv/social). A dedicated
        # gender detector should own this value; the LLM value should only be used
        # as a backup when the detector is unavailable. Until then we keep the
        # current behaviour and read it from the analysis JSON.
        gender = str(result_dict.get("detected_gender", "male")).lower()
        if gender not in ("male", "female"):
            gender = "male"

        if skip_gen:
            result_dict["upgrade_prompt"] = True
        else:
            trace["decisions"].append({
                "phase": "planning",
                "decision": "Single-pass",
                "reason": "Multi-pass is reserved in orchestrator.advanced and not wired into the runtime",
            })

            # v1.17 — optional GFPGAN face pre-clean for clearly blurry
            # inputs. Strictly opt-in via ``settings.gfpgan_preclean_enabled``
            # and further gated by Laplacian thresholds inside
            # ``prerestore_if_needed``. Failures fold back to the original
            # bytes — this stage must never take down the main pipeline.
            # v1.20: reuse the MediaPipe bbox from ``analyze_input_quality``
            # instead of re-detecting inside the prerestore / face-crop
            # chain — ``input_quality.face_bbox`` is the same detection
            # the input gate already accepted.
            face_bbox = getattr(input_quality, "face_bbox", None)
            with _trace_step(trace, "face_prerestore") as pre_entry:
                generation_bytes, prerestore_info = await prerestore_if_needed(
                    image_bytes, input_quality, face_bbox=face_bbox,
                )
                pre_entry["info"] = prerestore_info
            if prerestore_info.get("applied"):
                trace["decisions"].append({
                    "phase": "face_prerestore",
                    "decision": "GFPGAN pre-clean applied",
                    "reason": (
                        f"blur_face={prerestore_info.get('blur_face')}, "
                        f"blur_full={prerestore_info.get('blur_full')}"
                    ),
                })
                result_dict.setdefault(
                    "enhancement_prepipeline", {},
                )["gfpgan_preclean"] = True

            with _trace_step(trace, "generate_image"):
                await self._executor.single_pass(
                    mode, style, generation_bytes, result_dict, user_id,
                    task_id, trace,
                    gender=gender,
                    input_quality=input_quality,
                    variant_id=variant_id,
                )

            if (
                result_dict.get("generated_image_url")
                and mode in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL)
            ):
                if (context or {}).get("defer_delta_scoring"):
                    result_dict["delta_status"] = "pending"
                    trace["decisions"].append({
                        "phase": "delta_scoring",
                        "decision": "Deferred to separate job",
                        "reason": "defer_delta_scoring=True",
                    })
                else:
                    with _trace_step(trace, "post_gen_rescore"):
                        await self._delta_scorer.compute(mode, result_dict, user_id, task_id)

        trace["pipeline_ended_at"] = time.time()
        duration_s = trace["pipeline_ended_at"] - trace["pipeline_started_at"]
        trace["total_duration_ms"] = round(duration_s * 1000, 1)
        result_dict["pipeline_trace"] = trace

        pipeline_type = result_dict.get("enhancement", {}).get("pipeline_type", "analysis_only")
        PIPELINE_DURATION.labels(mode=mode.value, pipeline_type=pipeline_type).observe(duration_s)

        return await self._finalize(mode, result, result_dict, image_bytes, user_id, task_id)

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    async def _preprocess(
        self, image_bytes: bytes,
    ) -> tuple[bytes, dict, InputQualityReport]:
        # Both validate_and_normalize (Pillow decode/re-encode) and
        # analyze_input_quality (MediaPipe + Laplacian on NumPy arrays) are
        # purely CPU-bound and can take 100ms-2s. Running them directly in
        # the event loop blocks the worker for the whole duration — any
        # heartbeat, publish, or concurrent job in the same worker stalls.
        # Offload to a thread so the loop stays responsive.
        image_bytes, meta = await asyncio.to_thread(validate_and_normalize, image_bytes)

        report = await asyncio.to_thread(analyze_input_quality, image_bytes)
        if not report.can_generate:
            # First blocking issue gives the most actionable error; we also
            # attach machine codes in the exception args for API layer.
            primary = report.blocking[0]
            suffix = f" {primary.suggestion}".rstrip()
            raise ValueError(f"{primary.message}{suffix}")

        return image_bytes, meta, report

    # ------------------------------------------------------------------
    # Analysis (LLM scoring)
    # ------------------------------------------------------------------

    def _analysis_cache_key(self, mode: AnalysisMode, image_bytes: bytes, context: dict | None) -> str:
        """Deterministic cache key for LLM analysis based on image content and mode."""
        import hashlib
        h = hashlib.sha256(image_bytes).hexdigest()[:16]
        profession = (context or {}).get("profession", "")
        market_id = get_market_id(context, fallback=settings.resolved_market_id)
        return f"ratemeai:llm_cache:{market_id}:{mode.value}:{h}:{profession}"

    async def _analyze(self, mode: AnalysisMode, image_bytes: bytes, context: dict | None) -> tuple:
        cache_allowed = is_cache_allowed(context, default=True)
        if self._redis and cache_allowed:
            cache_key = self._analysis_cache_key(mode, image_bytes, context)
            try:
                import json as _json
                cached = await self._redis.get(cache_key)
                if cached:
                    result_dict = _json.loads(cached)
                    logger.info("LLM analysis cache hit for mode=%s", mode.value)
                    return result_dict, result_dict
            except Exception:
                logger.debug("LLM analysis cache miss/error for mode=%s", mode.value)

        service = self._router.get_service(mode)

        if mode == AnalysisMode.CV:
            profession = (context or {}).get("profession", "не указана")
            result = await service.analyze(image_bytes, profession=profession)
        else:
            result = await service.analyze(image_bytes)
        LLM_CALLS.labels(purpose=f"analyze_{mode.value}").inc()

        raw_dict = result if isinstance(result, dict) else (result.model_dump() if hasattr(result, "model_dump") else result)

        is_safe, reason = extract_nsfw_from_analysis(raw_dict)
        if not is_safe:
            raise ValueError(f"Фото не прошло модерацию: {reason}")

        if isinstance(result, RatingResult):
            result_dict = result.model_dump()
        else:
            result_dict = raw_dict

        if self._redis and cache_allowed:
            try:
                import json as _json
                await self._redis.set(cache_key, _json.dumps(result_dict), ex=600)
                logger.debug("Cached LLM analysis for mode=%s (10min TTL)", mode.value)
            except Exception:
                logger.debug("Failed to cache LLM analysis for mode=%s", mode.value)

        return result, result_dict

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

        # When delta scoring is deferred to a separate ARQ job, the
        # `perception_scores` map still holds pre-generation values at this
        # point. Persisting now would save the baseline as the user's personal
        # best, which defeats the purpose of the gamification tracker. The
        # deferred `compute_delta_scores` worker takes over the persist step
        # after `DeltaScorer.compute` has re-scored the generated image.
        if result_dict.get("delta_status") != "pending":
            await self._persist_perception_scores(mode, result_dict, user_id)

        return self._merger.merge(result_dict, share_card_url, user_id)

    async def _persist_perception_scores(
        self, mode: AnalysisMode, result_dict: dict, user_id: str,
    ) -> None:
        """Best-effort persistence of perception scores for gamification tracking."""
        if self._db_sessionmaker is None:
            return

        ps = result_dict.get("perception_scores")
        if not ps:
            return

        if hasattr(ps, "model_dump"):
            ps = ps.model_dump()

        style = result_dict.get("enhancement", {}).get("style", "default")

        try:
            from src.services.perception_tracker import update_best_scores

            async with self._db_sessionmaker() as session:
                async with session.begin():
                    await update_best_scores(session, user_id, mode.value, style, ps)
        except Exception:
            logger.debug("Perception tracking skipped (DB not available or error)", exc_info=True)
