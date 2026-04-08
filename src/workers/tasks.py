from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timezone

import redis.asyncio as redis_async
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import settings
from src.models.db import Task, UsageLog, User, CreditTransaction
from src.models.enums import AnalysisMode, TaskStatus
from src.orchestrator.pipeline import AnalysisPipeline
from src.providers.factory import get_image_gen, get_llm, get_storage
from src.utils.redis_keys import gen_image_cache_key, task_input_cache_key
from src.metrics import CREDITS_USED
from src.version import APP_VERSION

logger = logging.getLogger(__name__)


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

            analysis_result = await pipeline.execute(
                mode=AnalysisMode(task.mode),
                image_bytes=image_bytes,
                user_id=str(task.user_id),
                task_id=str(task.id),
                context=context or None,
                progress_callback=_progress_cb,
            )

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
                            ex=settings.task_input_redis_ttl_seconds,
                        )
                        logger.info("Staged generated image in Redis for task %s (%d bytes)", task_id, len(gen_bytes))
                        staged = True
                        break
                    except Exception:
                        logger.exception("Redis staging attempt %d failed for task %s", _attempt + 1, task_id)
                if not staged:
                    logger.error(
                        "All Redis staging attempts failed for task %s — bot will use URL fallback: %s",
                        task_id, gen_url,
                    )

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

            logger.info("Task %s completed", task_id)
            # Commit before Redis notify so GET /tasks sees final status when clients poll.
            await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "completed")
            except Exception:
                logger.warning("Failed to publish task_done for %s", task_id)

        except Exception as e:
            logger.exception("Task %s failed", task_id)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)[:500]
            await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "failed")
            except Exception:
                logger.warning("Failed to publish task_done (failed) for %s", task_id)


class WorkerSettings:
    functions = [process_analysis]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 200
