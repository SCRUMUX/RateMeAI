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
