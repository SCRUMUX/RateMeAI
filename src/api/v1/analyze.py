from __future__ import annotations

import uuid
from datetime import date

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, UsageLog, User
from src.models.enums import AnalysisMode, TaskStatus
from src.models.schemas import TaskCreated
from src.api.deps import get_db, check_rate_limit
from src.providers.factory import get_storage

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
    user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
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

    task = Task(
        user_id=user.id,
        mode=mode.value,
        status=TaskStatus.PENDING.value,
        input_image_path=image_key,
    )
    db.add(task)

    today = date.today()
    stmt = pg_insert(UsageLog).values(
        user_id=user.id, usage_date=today, count=1
    ).on_conflict_do_update(
        constraint="uq_usage_user_date",
        set_={"count": UsageLog.count + 1},
    )
    await db.execute(stmt)

    await db.commit()
    await db.refresh(task)

    arq = await _get_arq()
    await arq.enqueue_job("process_analysis", str(task.id))

    return TaskCreated(task_id=task.id)
