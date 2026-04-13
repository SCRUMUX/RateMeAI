from __future__ import annotations

import base64
import logging
import uuid

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, User, CreditTransaction
from src.models.enums import AnalysisMode, TaskStatus
from src.models.schemas import TaskCreated
from src.api.deps import get_db, get_redis, check_credits, check_rate_limit
from src.providers.factory import get_storage
from src.utils.redis_keys import task_input_cache_key, gen_image_cache_key
from prometheus_client import Counter

ANALYZE_REQUESTS = Counter(
    "ratemeai_analyze_requests_total",
    "Total POST /analyze requests (task creation attempts)",
    labelnames=["mode", "has_style", "has_enhancement_level"],
)

logger = logging.getLogger(__name__)

router = APIRouter()

_arq_pool: ArqRedis | None = None


async def _get_arq() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def _handle_edge_analysis(
    app_state,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    image_bytes: bytes,
    mode: str,
    style: str,
    profession: str,
    enhancement_level: int,
    pre_analysis_id: str,
) -> None:
    """In edge mode: proxy the AI task to the primary Railway backend.

    Runs as a background coroutine with its own DB session (the request session
    is already closed by the time long-running remote polling finishes).
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from src.services.remote_ai import get_remote_ai, RemoteAIError

    db_sessionmaker = app_state.db_sessionmaker
    redis: Redis = app_state.redis
    remote_ai = get_remote_ai()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    async with db_sessionmaker() as db:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            logger.error("Edge handler: task %s not found", task_id)
            return

        task.status = TaskStatus.PROCESSING.value
        await db.commit()

        async def _edge_progress(status: str, poll_count: int) -> None:
            """Relay polling status as progress events so edge SSE clients see updates."""
            try:
                estimated_total = 45
                current = min(poll_count * 2, estimated_total - 1)
                await redis.publish(
                    f"ratemeai:progress:{task_id}",
                    f"{status}:{current}:{estimated_total}",
                )
            except Exception:
                pass

        try:
            result_data = await remote_ai.submit_and_wait(
                image_b64=image_b64,
                mode=mode,
                style=style,
                profession=profession,
                enhancement_level=enhancement_level,
                pre_analysis_id=pre_analysis_id,
                edge_task_id=str(task_id),
                on_poll=_edge_progress,
            )

            remote_result = result_data.get("result") or {}
            gen_b64 = result_data.get("generated_image_b64")

            if gen_b64:
                gen_key = f"generated/{user_id}/{task_id}.jpg"
                storage = get_storage()
                await storage.upload(gen_key, base64.b64decode(gen_b64))

                await redis.set(
                    gen_image_cache_key(str(task_id)),
                    gen_b64,
                    ex=settings.gen_image_redis_ttl_seconds,
                )

                remote_result["generated_image_url"] = (
                    f"{settings.api_base_url.rstrip('/')}/storage/{gen_key}"
                )
                remote_result.pop("generated_image_b64", None)

            credit_pre_reserved = (task.context or {}).get("credit_pre_reserved", False)
            remote_result["credit_deducted"] = credit_pre_reserved

            from src.models.db import UsageLog
            from datetime import date as _date
            today = _date.today()
            usage_row = await db.execute(
                select(UsageLog).where(
                    UsageLog.user_id == user_id,
                    UsageLog.usage_date == today,
                )
            )
            usage_log = usage_row.scalar_one_or_none()
            if usage_log:
                usage_log.count += 1
            else:
                db.add(UsageLog(user_id=user_id, usage_date=today, count=1))

            task.result = remote_result
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "completed")
            except Exception:
                pass

        except Exception as exc:
            is_remote = isinstance(exc, RemoteAIError)
            if is_remote:
                logger.error("Edge AI proxy failed for task %s: %s", task_id, exc)
            else:
                logger.exception("Unexpected edge handler error for task %s", task_id)
            task.status = TaskStatus.FAILED.value
            task.error_message = (str(exc) if is_remote else f"Edge proxy error: {exc}")[:500]

            credit_pre_reserved = (task.context or {}).get("credit_pre_reserved", False)
            if credit_pre_reserved:
                u = await db.execute(
                    select(User).where(User.id == user_id).with_for_update()
                )
                fresh_user = u.scalar_one()
                fresh_user.image_credits += 1
                db.add(CreditTransaction(
                    user_id=user_id,
                    amount=1,
                    balance_after=fresh_user.image_credits,
                    tx_type="refund_failed_task",
                ))
                logger.info("Refunded 1 credit to user %s for failed edge task %s", user_id, task_id)

            await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "failed")
            except Exception:
                pass


@router.post("", response_model=TaskCreated, status_code=202)
async def create_analysis(
    request: Request,
    image: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.RATING),
    style: str = Form(""),
    profession: str = Form(""),
    enhancement_level: int = Form(0),
    pre_analysis_id: str = Form(""),
    user: User = Depends(check_credits),
    _rate_limited: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    ANALYZE_REQUESTS.labels(
        mode=mode.value,
        has_style=str(bool(style.strip())).lower(),
        has_enhancement_level=str(enhancement_level > 0).lower(),
    ).inc()

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
    if pre_analysis_id.strip():
        ctx["pre_analysis_id"] = pre_analysis_id.strip()
    if getattr(user, "_credit_reserved", False):
        ctx["credit_pre_reserved"] = True

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

    credits_remaining = getattr(user, "_credits_remaining", None)
    headers = {}
    if credits_remaining is not None:
        headers["X-Credits-Remaining"] = str(credits_remaining)

    if settings.is_edge:
        import asyncio

        asyncio.create_task(
            _handle_edge_analysis(
                app_state=request.app.state,
                task_id=task.id,
                user_id=user.id,
                image_bytes=image_bytes,
                mode=task.mode,
                style=style.strip(),
                profession=profession.strip(),
                enhancement_level=enhancement_level,
                pre_analysis_id=pre_analysis_id.strip(),
            )
        )
        body = TaskCreated(task_id=task.id, status=TaskStatus.PENDING, estimated_seconds=30)
        return JSONResponse(
            content=body.model_dump(mode="json"),
            status_code=202,
            headers=headers,
        )

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

    body = TaskCreated(task_id=task.id, status=TaskStatus.PENDING, estimated_seconds=15)
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=202,
        headers=headers,
    )
