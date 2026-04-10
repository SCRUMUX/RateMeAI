from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from src.config import settings
from src.metrics import PIPELINE_DURATION, LLM_CALLS
from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult
from src.orchestrator.executor import ImageGenerationExecutor, DeltaScorer
from src.orchestrator.merger import ResultMerger
from src.orchestrator.model_router import ModelRouter, build_model_registry
from src.orchestrator.planner import PipelinePlanner
from src.orchestrator.router import ModeRouter
from src.providers.base import ImageGenProvider, LLMProvider, StorageProvider
from src.prompts.engine import PromptEngine
from src.services.share import ShareCardGenerator
from src.utils.humanize import SCORE_FLOOR, PERCEPTION_FLOOR, humanize_result_scores
from src.utils.image import validate_and_normalize, has_face_heuristic, estimate_blur_score
from src.utils.redis_keys import embedding_cache_key, preanalysis_cache_key
from src.utils.security import extract_nsfw_from_analysis

logger = logging.getLogger(__name__)

_SCORE_FLOOR = SCORE_FLOOR
_PERCEPTION_FLOOR = PERCEPTION_FLOOR


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
        self._segmentation = None
        self._planner = PipelinePlanner()
        self._model_router: ModelRouter = build_model_registry(
            image_gen,
            cost_reve=settings.model_cost_reve,
            cost_replicate=settings.model_cost_replicate,
        )
        self._executor = ImageGenerationExecutor(
            image_gen=image_gen,
            prompt_engine=self._prompt_engine,
            model_router=self._model_router,
            storage=storage,
            identity_svc_getter=self._get_identity_service,
            gate_runner_getter=self._get_gate_runner,
            embedding_getter=self._get_or_compute_embedding,
            segmentation_getter=self._get_segmentation_service,
        )
        self._delta_scorer = DeltaScorer(router=self._router, storage=storage, redis=redis)

    def _get_identity_service(self):
        if self._identity is None:
            try:
                from src.services.identity import IdentityService
                self._identity = IdentityService(threshold=settings.identity_threshold)
            except ImportError:
                logger.warning("InsightFace not installed — identity gate disabled")
        return self._identity

    @property
    def identity_available(self) -> bool:
        return self._get_identity_service() is not None

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
            image_bytes, img_meta = await self._preprocess(image_bytes)

        with _trace_step(trace, "analyze"):
            pre_id = (context or {}).get("pre_analysis_id")
            cached_pre = None
            if pre_id and self._redis:
                try:
                    import json as _json
                    raw = await self._redis.get(preanalysis_cache_key(pre_id))
                    if raw:
                        cached_pre = _json.loads(raw)
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
        orig_w = img_meta.get("original_width", 0)
        orig_h = img_meta.get("original_height", 0)
        if orig_w < 400 or orig_h < 400:
            warnings.append(
                "Фото имеет низкое разрешение. "
                "Загрузи фото в более высоком качестве для лучшего результата."
            )

        blur_score = estimate_blur_score(image_bytes)
        if 0 <= blur_score < 100:
            warnings.append(
                "Фото выглядит размытым. "
                "Загрузи более чёткое фото для лучшего результата."
            )

        style = (context or {}).get("style", "")
        skip_gen = (context or {}).get("skip_image_gen", False)
        enhancement_level = int((context or {}).get("enhancement_level", 0))

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
                    analysis_result=result_dict,
                    enhancement_level=enhancement_level,
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
                    await self._executor.execute_plan(
                        plan, mode, style, image_bytes, result_dict,
                        user_id, task_id, trace, enhancement_level, progress_callback,
                    )
            else:
                trace["decisions"].append({
                    "phase": "planning",
                    "decision": "Single-pass fallback",
                    "reason": "Multi-pass disabled or mode does not support it",
                })
                with _trace_step(trace, "generate_image"):
                    await self._executor.single_pass(
                        mode, style, image_bytes, result_dict, user_id, task_id, trace,
                    )

            if (
                result_dict.get("generated_image_url")
                and mode in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL)
            ):
                with _trace_step(trace, "post_gen_rescore"):
                    await self._delta_scorer.compute(mode, image_bytes, result_dict, user_id, task_id)

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

    async def _preprocess(self, image_bytes: bytes) -> tuple[bytes, dict]:
        image_bytes, meta = validate_and_normalize(image_bytes)

        if not has_face_heuristic(image_bytes):
            raise ValueError("На фото не обнаружено лицо. Загрузи портретное фото.")

        return image_bytes, meta

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
        LLM_CALLS.labels(purpose=f"analyze_{mode.value}").inc()

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
