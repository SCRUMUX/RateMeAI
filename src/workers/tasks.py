from __future__ import annotations

import asyncio
import base64
import logging
from datetime import date, datetime, timezone, timedelta

import redis.asyncio as redis_async
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import settings
from src.models.db import Task, UsageLog, User, CreditTransaction
from src.models.enums import AnalysisMode, TaskStatus
from src.orchestrator.pipeline import AnalysisPipeline
from src.providers.factory import get_image_gen, get_llm, get_storage
from src.utils.redis_keys import gen_image_cache_key, task_input_cache_key
from src.metrics import (
    CREDITS_USED, TASKS_COMPLETED, TASKS_FAILED, TASKS_RECONCILED,
    PIPELINE_RETRIES, TASKS_IN_PROCESSING, COMPLETED_WITHOUT_IMAGE,
)
from src.version import APP_VERSION

logger = logging.getLogger(__name__)

_MAX_PIPELINE_RETRIES = 2
_RETRY_BACKOFF_BASE = 3.0
_TRANSIENT_MARKERS = ("rate limit", "timeout", "connect", "temporarily", "503", "429")
STUCK_TASK_THRESHOLD_MINUTES = 10


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


async def startup(ctx: dict):
    engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=10)
    ctx["db_sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["engine"] = engine

    ctx["redis"] = redis_async.from_url(settings.redis_url, decode_responses=True)

    ctx["llm"] = get_llm()
    ctx["storage"] = get_storage()
    ctx["image_gen"] = get_image_gen()
    ctx["pipeline"] = AnalysisPipeline(
        llm=ctx["llm"],
        storage=ctx["storage"],
        image_gen=ctx["image_gen"],
        redis=ctx["redis"],
        db_sessionmaker=ctx["db_sessionmaker"],
    )

    st = ctx["storage"]
    if hasattr(st, "base_path"):
        logger.info("Worker storage base_path=%s", st.base_path)
    if settings.is_production and not settings.openrouter_api_key.strip():
        logger.error("OPENROUTER_API_KEY is empty — tasks will fail at LLM step")

    identity_ok = ctx["pipeline"].identity_available
    if not identity_ok:
        logger.error(
            "InsightFace NOT loaded — identity gate DISABLED. "
            "Generated images may show a different person. Install insightface to fix."
        )
    sha = (settings.deploy_git_sha or "").strip()
    logger.info(
        "Worker started RateMeAI version=%s%s",
        APP_VERSION,
        f" git={sha[:12]}" if sha else "",
    )


async def shutdown(ctx: dict):
    if "llm" in ctx:
        await ctx["llm"].close()
    if "image_gen" in ctx:
        await ctx["image_gen"].close()
    if "redis" in ctx:
        await ctx["redis"].close()
    if "engine" in ctx:
        await ctx["engine"].dispose()
    logger.info("Worker stopped")


async def process_analysis(ctx: dict, task_id: str):
    db_sessionmaker = ctx["db_sessionmaker"]
    pipeline: AnalysisPipeline = ctx["pipeline"]
    storage = ctx["storage"]
    redis = ctx["redis"]

    async with db_sessionmaker() as db:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if task is None:
            logger.error("Task %s not found", task_id)
            return

        task.status = TaskStatus.PROCESSING.value
        await db.commit()

        try:
            ck = task_input_cache_key(task_id)
            b64 = await redis.get(ck)
            if b64:
                image_bytes = base64.b64decode(b64)
                await redis.delete(ck)
                logger.info("Task %s input loaded from Redis cache", task_id)
            else:
                image_bytes = await storage.download(task.input_image_path)

            u_row = await db.execute(
                select(User).where(User.id == task.user_id)
            )
            task_user = u_row.scalar_one()
            has_credits = task_user.image_credits > 0

            context: dict = dict(task.context or {})
            if not has_credits:
                context["skip_image_gen"] = True

            async def _progress_cb(step_name: str, current: int, total: int):
                try:
                    await redis.publish(
                        f"ratemeai:progress:{task.id}",
                        f"{step_name}:{current}:{total}",
                    )
                except Exception:
                    pass

            last_exc: Exception | None = None
            analysis_result = None
            for attempt in range(_MAX_PIPELINE_RETRIES + 1):
                try:
                    analysis_result = await pipeline.execute(
                        mode=AnalysisMode(task.mode),
                        image_bytes=image_bytes,
                        user_id=str(task.user_id),
                        task_id=str(task.id),
                        context=context or None,
                        progress_callback=_progress_cb,
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < _MAX_PIPELINE_RETRIES and _is_transient(exc):
                        PIPELINE_RETRIES.inc()
                        wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "Task %s transient error (attempt %d/%d), retrying in %.1fs: %s",
                            task_id, attempt + 1, _MAX_PIPELINE_RETRIES + 1, wait, exc,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise
            if analysis_result is None:
                raise last_exc or RuntimeError("Pipeline returned no result")

            gen_url = analysis_result.get("generated_image_url")
            if gen_url:
                gkey = f"generated/{task.user_id}/{task.id}.jpg"
                staged = False
                for _attempt in range(2):
                    try:
                        gen_bytes = await storage.download(gkey)
                        b64_gen = base64.b64encode(gen_bytes).decode()
                        await redis.set(
                            gen_image_cache_key(str(task.id)),
                            b64_gen,
                            ex=settings.gen_image_redis_ttl_seconds,
                        )
                        logger.info("Staged generated image in Redis for task %s (%d bytes)", task_id, len(gen_bytes))
                        staged = True
                        break
                    except Exception:
                        logger.exception("Redis staging attempt %d failed for task %s", _attempt + 1, task_id)
                if not staged:
                    logger.error(
                        "All Redis staging attempts failed for task %s — saving b64 to DB as fallback",
                        task_id,
                    )
                    try:
                        gen_bytes_fb = await storage.download(gkey)
                        analysis_result["generated_image_b64"] = base64.b64encode(gen_bytes_fb).decode()
                    except Exception:
                        logger.exception("DB b64 fallback also failed for task %s", task_id)

                skip_deduct = context.get("skip_credit_deduct", False)
                if skip_deduct:
                    logger.info("Skipping credit deduction for edge-proxied task %s", task_id)
                    analysis_result["credit_deducted"] = False
                else:
                    try:
                        u = await db.execute(
                            select(User).where(User.id == task.user_id).with_for_update()
                        )
                        user = u.scalar_one()
                        if user.image_credits > 0:
                            user.image_credits -= 1
                            db.add(CreditTransaction(
                                user_id=task.user_id,
                                amount=-1,
                                balance_after=user.image_credits,
                                tx_type="generation",
                            ))
                            CREDITS_USED.inc()
                            logger.info("Deducted 1 image credit for user %s, remaining=%d", task.user_id, user.image_credits)
                            analysis_result["credit_deducted"] = True
                        else:
                            logger.warning("No credits to deduct for user %s (balance=0), image was generated for free", task.user_id)
                            analysis_result["credit_deducted"] = False
                    except Exception:
                        logger.exception("Failed to deduct image credit for task %s", task_id)
                        analysis_result["credit_deducted"] = False

            analysis_result["enhancement_level"] = context.get("enhancement_level", 0)

            gen_url = analysis_result.get("generated_image_url")
            analysis_result["has_generated_image"] = bool(gen_url)
            if not gen_url:
                if context.get("skip_image_gen"):
                    analysis_result["no_image_reason"] = "no_credits"
                elif analysis_result.get("image_gen_error"):
                    analysis_result["no_image_reason"] = "generation_error"
                elif analysis_result.get("upgrade_prompt"):
                    analysis_result["no_image_reason"] = "upgrade_required"
                else:
                    analysis_result["no_image_reason"] = "not_applicable"

            task.result = analysis_result
            task.share_card_path = analysis_result.get("share", {}).get("card_url")
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.now(timezone.utc)

            today = date.today()
            stmt = pg_insert(UsageLog).values(
                user_id=task.user_id, usage_date=today, count=1
            ).on_conflict_do_update(
                constraint="uq_usage_user_date",
                set_={"count": UsageLog.count + 1},
            )
            await db.execute(stmt)

            has_image = bool(analysis_result.get("generated_image_url"))
            TASKS_COMPLETED.labels(has_image=str(has_image).lower()).inc()
            if not has_image:
                reason = analysis_result.get("no_image_reason", "unknown")
                COMPLETED_WITHOUT_IMAGE.labels(reason=reason).inc()

            logger.info("Task %s completed (has_image=%s)", task_id, has_image)
            await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "completed")
            except Exception:
                logger.warning("Failed to publish task_done for %s", task_id)

        except Exception as e:
            logger.exception("Task %s failed", task_id)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)[:500]
            fail_reason = "transient" if _is_transient(e) else "permanent"
            TASKS_FAILED.labels(reason=fail_reason).inc()
            await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "failed")
            except Exception:
                logger.warning("Failed to publish task_done (failed) for %s", task_id)


async def reconcile_stuck_tasks(ctx: dict):
    """Find tasks stuck in 'processing' beyond the SLA and mark them failed."""
    db_sessionmaker = ctx["db_sessionmaker"]
    redis = ctx["redis"]
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_TASK_THRESHOLD_MINUTES)

    async with db_sessionmaker() as db:
        all_processing = await db.execute(
            select(Task).where(Task.status == TaskStatus.PROCESSING.value)
        )
        TASKS_IN_PROCESSING.set(len(all_processing.scalars().all()))

        rows = await db.execute(
            select(Task).where(
                Task.status == TaskStatus.PROCESSING.value,
                Task.created_at < threshold,
            )
        )
        stuck_tasks = rows.scalars().all()
        for task in stuck_tasks:
            task.status = TaskStatus.FAILED.value
            task.error_message = (
                f"Task exceeded {STUCK_TASK_THRESHOLD_MINUTES}min processing SLA "
                f"and was marked failed by reconciler."
            )
            TASKS_RECONCILED.inc()
            TASKS_FAILED.labels(reason="stuck_timeout").inc()
            logger.warning("Reconciler: task %s stuck since %s, marking failed", task.id, task.created_at)
            try:
                await redis.publish(f"ratemeai:task_done:{task.id}", "failed")
            except Exception:
                pass
        if stuck_tasks:
            await db.commit()
            logger.info("Reconciler: marked %d stuck tasks as failed", len(stuck_tasks))


class WorkerSettings:
    functions = [process_analysis]
    cron_jobs = [
        cron(reconcile_stuck_tasks, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 200
