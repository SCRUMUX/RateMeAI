from __future__ import annotations

import asyncio
import base64
import logging
from datetime import date, datetime, timezone

import redis.asyncio as redis_async
from arq.connections import RedisSettings, create_pool
from arq.cron import cron
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import settings
from src.models.db import Task, UsageLog, User, CreditTransaction
from src.models.enums import AnalysisMode, TaskStatus
from src.services.reconciliation import STUCK_TASK_THRESHOLD_MINUTES  # noqa: F401 — re-export for backward compat
from src.services.task_contract import get_market_id, should_delete_after_process
from src.orchestrator.pipeline import AnalysisPipeline
from src.providers.factory import get_image_gen, get_llm, get_storage
from src.utils.redis_keys import (
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL,
    gen_image_cache_key,
    gen_image_cache_keys,
    task_input_cache_keys,
)
from src.metrics import (
    CREDITS_USED, TASKS_COMPLETED, TASKS_FAILED,
    PIPELINE_RETRIES, COMPLETED_WITHOUT_IMAGE,
)
from src.version import APP_VERSION
from src.tracing import async_span

logger = logging.getLogger(__name__)

_MAX_PIPELINE_RETRIES = 2
_RETRY_BACKOFF_BASE = 3.0
_TRANSIENT_MARKERS = ("rate limit", "timeout", "connect", "temporarily", "503", "429")


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
    ctx["arq"] = await create_pool(RedisSettings.from_dsn(settings.redis_url))

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
    import time
    await ctx["redis"].set(WORKER_HEARTBEAT_KEY, str(time.time()), ex=WORKER_HEARTBEAT_TTL)

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
    if "arq" in ctx:
        await ctx["arq"].close()
    if "engine" in ctx:
        await ctx["engine"].dispose()
    logger.info("Worker stopped")


async def _delete_storage_key(storage, key: str | None) -> None:
    if not key:
        return
    try:
        await storage.delete(key)
    except FileNotFoundError:
        pass
    except Exception:
        logger.warning("Failed to delete storage key %s", key, exc_info=True)


async def _cleanup_ephemeral_artifacts(
    storage,
    redis,
    task: Task,
    market_id: str,
    *,
    include_generated: bool,
) -> None:
    for cache_key in task_input_cache_keys(str(task.id), market_id):
        try:
            await redis.delete(cache_key)
        except Exception:
            logger.debug("Failed to delete input cache key %s", cache_key, exc_info=True)

    if not should_delete_after_process(task.context):
        return

    await _delete_storage_key(storage, task.input_image_path)

    if include_generated:
        for cache_key in gen_image_cache_keys(str(task.id), market_id):
            try:
                await redis.delete(cache_key)
            except Exception:
                logger.debug("Failed to delete generated cache key %s", cache_key, exc_info=True)
        await _delete_storage_key(storage, f"generated/{task.user_id}/{task.id}.jpg")


async def process_analysis(ctx: dict, task_id: str):
    async with async_span("worker.process_analysis", {"task.id": task_id}):
        await _process_analysis_inner(ctx, task_id)


async def _process_analysis_inner(ctx: dict, task_id: str):
    db_sessionmaker = ctx["db_sessionmaker"]
    pipeline: AnalysisPipeline = ctx["pipeline"]
    storage = ctx["storage"]
    redis = ctx["redis"]
    arq = ctx.get("arq")

    async with db_sessionmaker() as db:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if task is None:
            logger.error("Task %s not found", task_id)
            return

        task.status = TaskStatus.PROCESSING.value
        credit_pre_reserved = (task.context or {}).get("credit_pre_reserved", False)
        market_id = get_market_id(task.context, fallback=settings.resolved_market_id)
        await db.commit()

        try:
            image_bytes = None
            for cache_key in task_input_cache_keys(task_id, market_id):
                b64 = await redis.get(cache_key)
                if not b64:
                    continue
                image_bytes = base64.b64decode(b64)
                logger.info("Task %s input loaded from Redis cache (%s)", task_id, cache_key)
                break
            if image_bytes is None:
                image_bytes = await storage.download(task.input_image_path)

            u_row = await db.execute(
                select(User).where(User.id == task.user_id)
            )
            task_user = u_row.scalar_one()
            has_credits = credit_pre_reserved or task_user.image_credits > 0

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
                            gen_image_cache_key(str(task.id), market_id),
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
                elif credit_pre_reserved:
                    CREDITS_USED.inc()
                    logger.info("Credit was pre-reserved at request time for task %s", task_id)
                    analysis_result["credit_deducted"] = True
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

            if analysis_result.get("delta_status") == "pending" and arq is not None:
                try:
                    await arq.enqueue_job("compute_delta_scores", str(task.id))
                except Exception:
                    logger.warning("Failed to enqueue deferred delta scoring for %s", task_id, exc_info=True)

            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "completed")
            except Exception:
                logger.warning("Failed to publish task_done for %s", task_id)

            await _cleanup_ephemeral_artifacts(
                storage,
                redis,
                task,
                market_id,
                include_generated=analysis_result.get("delta_status") != "pending",
            )

        except Exception as e:
            logger.exception("Task %s failed", task_id)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)[:500]
            fail_reason = "transient" if _is_transient(e) else "permanent"
            TASKS_FAILED.labels(reason=fail_reason).inc()

            if credit_pre_reserved:
                try:
                    u = await db.execute(
                        select(User).where(User.id == task.user_id).with_for_update()
                    )
                    user = u.scalar_one()
                    user.image_credits += 1
                    db.add(CreditTransaction(
                        user_id=task.user_id,
                        amount=1,
                        balance_after=user.image_credits,
                        tx_type="refund_failed_task",
                    ))
                    logger.info("Refunded 1 credit to user %s for failed task %s", task.user_id, task_id)
                except Exception:
                    logger.exception("Failed to refund credit for task %s", task_id)

            await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "failed")
            except Exception:
                logger.warning("Failed to publish task_done (failed) for %s", task_id)

            await _cleanup_ephemeral_artifacts(
                storage,
                redis,
                task,
                market_id,
                include_generated=True,
            )


async def compute_delta_scores(ctx: dict, task_id: str):
    """Deferred delta scoring: re-analyze the generated image and patch results.

    Called as a separate ARQ job so the main pipeline can deliver results faster.
    """
    db_sessionmaker = ctx["db_sessionmaker"]
    pipeline: AnalysisPipeline = ctx["pipeline"]
    storage = ctx["storage"]
    redis = ctx["redis"]

    async with db_sessionmaker() as db:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            logger.warning("Delta scoring: task %s not found", task_id)
            return
        market_id = get_market_id(task.context, fallback=settings.resolved_market_id)
        if task.status != TaskStatus.COMPLETED.value:
            logger.warning("Delta scoring: task %s not in completed state (%s)", task_id, task.status)
            return

        task_result = task.result or {}
        if task_result.get("delta_status") != "pending":
            logger.info("Delta scoring: task %s not marked for deferred scoring", task_id)
            return

        mode_str = task.mode
        try:
            mode = AnalysisMode(mode_str)
        except ValueError:
            logger.warning("Delta scoring: unknown mode %s for task %s", mode_str, task_id)
            return

        try:
            input_bytes = await storage.download(task.input_image_path)
        except Exception:
            logger.exception("Delta scoring: failed to download input for task %s", task_id)
            return

        try:
            await pipeline._delta_scorer.compute(mode, input_bytes, task_result, str(task.user_id), task_id)
            task_result["delta_status"] = "completed"
            task.result = task_result
            await db.commit()

            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "delta_updated")
            except Exception:
                pass

            logger.info("Delta scoring completed for task %s", task_id)
            await _cleanup_ephemeral_artifacts(
                storage,
                redis,
                task,
                market_id,
                include_generated=True,
            )
        except Exception:
            logger.exception("Delta scoring failed for task %s", task_id)
            task_result["delta_status"] = "failed"
            task_result["delta_error"] = "deferred_rescoring_failed"
            task.result = task_result
            await db.commit()
            await _cleanup_ephemeral_artifacts(
                storage,
                redis,
                task,
                market_id,
                include_generated=True,
            )


async def worker_heartbeat(ctx: dict):
    """Update Redis heartbeat key so health checks can verify the worker is alive."""
    import time
    redis = ctx["redis"]
    await redis.set(WORKER_HEARTBEAT_KEY, str(time.time()), ex=WORKER_HEARTBEAT_TTL)


async def reconcile_stuck_tasks_cron(ctx: dict):
    """Cron wrapper: delegates to shared reconciliation logic."""
    from src.services.reconciliation import reconcile_stuck_tasks
    await reconcile_stuck_tasks(
        ctx["db_sessionmaker"],
        ctx["redis"],
        source="worker",
        track_processing_gauge=True,
    )


class WorkerSettings:
    functions = [process_analysis, compute_delta_scores]
    cron_jobs = [
        cron(reconcile_stuck_tasks_cron, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(worker_heartbeat, second={0, 30}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 200
