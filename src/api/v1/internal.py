"""Internal API for edge→primary AI task proxying.

These endpoints are called by the RU edge server to delegate AI processing
to the primary Railway backend. Protected by INTERNAL_API_KEY.
"""
from __future__ import annotations

import base64
import logging
import uuid

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task
from src.models.enums import AnalysisMode, TaskStatus
from src.api.deps import get_db, get_redis

logger = logging.getLogger(__name__)
router = APIRouter()

_arq_pool: ArqRedis | None = None


async def _get_arq() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def _verify_internal_key(x_internal_key: str = Header(...)) -> str:
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="Internal API not configured")
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    return x_internal_key


# ── Schemas ──

class RemotePreAnalyzeRequest(BaseModel):
    image_b64: str
    mode: AnalysisMode = AnalysisMode.DATING
    profession: str = ""
    skip_validation: bool = False


class RemoteAnalysisRequest(BaseModel):
    image_b64: str
    mode: AnalysisMode = AnalysisMode.RATING
    style: str = ""
    profession: str = ""
    enhancement_level: int = 0
    pre_analysis_id: str = ""
    edge_task_id: str = Field("", description="Task ID from the edge server for tracing")


class RemoteAnalysisResponse(BaseModel):
    remote_task_id: uuid.UUID
    status: str = "pending"


class RemoteTaskStatusResponse(BaseModel):
    status: str
    result: dict | None = None
    error_message: str | None = None
    generated_image_b64: str | None = None


# ── Endpoints ──

@router.post("/process-analysis", response_model=RemoteAnalysisResponse, status_code=202)
async def process_analysis_remote(
    request: RemoteAnalysisRequest,
    _key: str = Depends(_verify_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Accept an AI analysis task from the edge server and enqueue it for processing."""
    try:
        image_bytes = base64.b64decode(request.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    from src.providers.factory import get_storage

    internal_user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "edge-proxy.internal")

    storage = get_storage()
    image_key = f"inputs/{internal_user_id}/{uuid.uuid4()}.jpg"
    await storage.upload(image_key, image_bytes)

    ctx: dict = {}
    if request.style.strip():
        ctx["style"] = request.style.strip()
    if request.profession.strip():
        ctx["profession"] = request.profession.strip()
    if request.enhancement_level > 0:
        ctx["enhancement_level"] = request.enhancement_level
    if request.pre_analysis_id.strip():
        ctx["pre_analysis_id"] = request.pre_analysis_id.strip()
    if request.edge_task_id:
        ctx["edge_task_id"] = request.edge_task_id

    ctx["remote_origin"] = "edge"
    ctx["skip_credit_deduct"] = True

    task = Task(
        user_id=internal_user_id,
        mode=request.mode.value,
        status=TaskStatus.PENDING.value,
        input_image_path=image_key,
        context=ctx or None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from src.utils.redis_keys import task_input_cache_key

    cache_key = task_input_cache_key(str(task.id))
    try:
        await redis.set(
            cache_key,
            request.image_b64,
            ex=settings.task_input_redis_ttl_seconds,
        )
    except Exception:
        logger.exception("Redis error staging remote task input for %s", task.id)
        raise HTTPException(status_code=500, detail="Failed to stage task input")

    arq = await _get_arq()
    await arq.enqueue_job("process_analysis", str(task.id))

    logger.info(
        "Accepted remote analysis task %s (edge_task=%s, mode=%s)",
        task.id, request.edge_task_id, request.mode.value,
    )
    return RemoteAnalysisResponse(remote_task_id=task.id, status="pending")


@router.get("/task/{task_id}/status", response_model=RemoteTaskStatusResponse)
async def get_remote_task_status(
    task_id: uuid.UUID,
    _key: str = Depends(_verify_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Poll AI task status. Returns result + generated image as base64 when done."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    response = RemoteTaskStatusResponse(
        status=task.status,
        error_message=task.error_message,
    )

    if task.status == TaskStatus.COMPLETED.value and task.result:
        response.result = task.result

        from src.utils.redis_keys import gen_image_cache_key

        b64 = await redis.get(gen_image_cache_key(str(task.id)))
        if b64:
            response.generated_image_b64 = b64
        elif task.result.get("generated_image_b64"):
            response.generated_image_b64 = task.result["generated_image_b64"]

    return response


@router.post("/pre-analyze")
async def pre_analyze_remote(
    request: RemotePreAnalyzeRequest,
    _key: str = Depends(_verify_internal_key),
    redis: Redis = Depends(get_redis),
):
    """Run pre-analysis on the primary backend for the edge server."""
    try:
        image_bytes = base64.b64decode(request.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    if not request.skip_validation:
        from src.utils.image import validate_and_normalize, has_face_heuristic

        try:
            image_bytes, _meta = validate_and_normalize(image_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        if not has_face_heuristic(image_bytes):
            raise HTTPException(
                status_code=400,
                detail="На фото не обнаружено лицо. Загрузи портретное фото.",
            )

    from src.orchestrator.router import ModeRouter
    from src.providers.factory import get_llm
    from src.prompts.engine import PromptEngine
    from src.utils.humanize import humanize_result_scores
    from src.utils.security import extract_nsfw_from_analysis
    from src.models.schemas import RatingResult
    from src.metrics import LLM_CALLS

    llm = get_llm()
    mode_router = ModeRouter(llm, PromptEngine())
    service = mode_router.get_service(request.mode)

    if request.mode == AnalysisMode.CV:
        prof = request.profession.strip() or "не указана"
        result = await service.analyze(image_bytes, profession=prof)
    else:
        result = await service.analyze(image_bytes)
    LLM_CALLS.labels(purpose=f"preanalyze_{request.mode.value}").inc()

    raw_dict = result if isinstance(result, dict) else (
        result.model_dump() if hasattr(result, "model_dump") else result
    )

    is_safe, reason = extract_nsfw_from_analysis(raw_dict)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Фото не прошло модерацию: {reason}")

    if isinstance(result, RatingResult):
        result_dict = result.model_dump()
    else:
        result_dict = raw_dict

    pre_id = str(uuid.uuid4())
    humanize_result_scores(result_dict, pre_id)
    result_dict["_scores_humanized"] = True

    from src.api.v1.pre_analyze import _extract_composite_score

    score = _extract_composite_score(request.mode, result_dict)
    perception = result_dict.get("perception_scores", {})
    if hasattr(perception, "model_dump"):
        perception = perception.model_dump()

    insights = result_dict.get("perception_insights", [])
    if insights and hasattr(insights[0], "model_dump"):
        insights = [i.model_dump() for i in insights]

    opportunities = result_dict.get("enhancement_opportunities", [])

    from src.utils.redis_keys import preanalysis_cache_key
    import json as _json

    _PRE_ANALYSIS_TTL = 1800
    try:
        await redis.set(
            preanalysis_cache_key(pre_id),
            _json.dumps(result_dict, default=str),
            ex=_PRE_ANALYSIS_TTL,
        )
    except Exception:
        logger.exception("Failed to cache pre-analysis %s on primary", pre_id)

    return {
        "pre_analysis_id": pre_id,
        "mode": request.mode.value,
        "first_impression": result_dict.get("first_impression", result_dict.get("analysis", "")),
        "score": score,
        "perception_scores": perception,
        "perception_insights": insights,
        "enhancement_opportunities": opportunities,
    }
