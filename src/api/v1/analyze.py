from __future__ import annotations

import base64
import logging
import uuid

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, User
from src.models.enums import AnalysisMode, TaskStatus
from src.models.schemas import TaskCreated
from src.api.deps import get_db, get_redis, check_rate_limit
from src.providers.factory import get_storage
from src.utils.redis_keys import task_input_cache_key

logger = logging.getLogger(__name__)

router = APIRouter()

_arq_pool: ArqRedis | None = None


async def _get_arq() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


@router.post("", response_model=TaskCreated, status_code=202)
async def create_analysis(
    image: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.RATING),
    style: str = Form(""),
    profession: str = Form(""),
    enhancement_level: int = Form(0),
    user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    storage = get_storage()
    image_key = f"inputs/{user.id}/{uuid.uuid4()}.jpg"
    await storage.upload(image_key, image_bytes)

    ctx: dict = {}
    if style.strip():
        ctx["style"] = style.strip()
    if profession.strip():
        ctx["profession"] = profession.strip()
    if enhancement_level > 0:
        ctx["enhancement_level"] = enhancement_level

    task = Task(
        user_id=user.id,
        mode=mode.value,
        status=TaskStatus.PENDING.value,
        input_image_path=image_key,
        context=ctx or None,
    )
    db.add(task)

    await db.commit()
    await db.refresh(task)

    cache_key = task_input_cache_key(str(task.id))
    try:
        await redis.set(
            cache_key,
            base64.b64encode(image_bytes).decode("ascii"),
            ex=settings.task_input_redis_ttl_seconds,
        )
        if style.strip():
            await redis.set(
                f"ratemeai:style:{task.id}",
                style.strip(),
                ex=settings.task_input_redis_ttl_seconds,
            )
    except Exception:
        logger.exception("Redis error staging task input for %s", task.id)
        raise HTTPException(status_code=500, detail="Failed to stage task input") from None

    arq = await _get_arq()
    await arq.enqueue_job("process_analysis", str(task.id))

    rl = getattr(user, "_rate_limit_info", None)
    headers = {}
    if rl:
        headers["X-RateLimit-Limit"] = str(rl["limit"])
        headers["X-RateLimit-Remaining"] = str(rl["remaining"])

    body = TaskCreated(task_id=task.id, status=TaskStatus.PENDING, estimated_seconds=15)
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=202,
        headers=headers,
    )
