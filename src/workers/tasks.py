from __future__ import annotations

import logging
from datetime import datetime, timezone

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import settings
from src.models.db import Task
from src.models.enums import AnalysisMode, TaskStatus
from src.orchestrator.pipeline import AnalysisPipeline
from src.providers.factory import get_llm, get_storage

logger = logging.getLogger(__name__)


async def startup(ctx: dict):
    engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=10)
    ctx["db_sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["engine"] = engine

    ctx["llm"] = get_llm()
    ctx["storage"] = get_storage()
    ctx["pipeline"] = AnalysisPipeline(llm=ctx["llm"], storage=ctx["storage"])

    logger.info("Worker started")


async def shutdown(ctx: dict):
    if "llm" in ctx:
        await ctx["llm"].close()
    if "engine" in ctx:
        await ctx["engine"].dispose()
    logger.info("Worker stopped")


async def process_analysis(ctx: dict, task_id: str):
    db_sessionmaker = ctx["db_sessionmaker"]
    pipeline: AnalysisPipeline = ctx["pipeline"]
    storage = ctx["storage"]

    async with db_sessionmaker() as db:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if task is None:
            logger.error("Task %s not found", task_id)
            return

        task.status = TaskStatus.PROCESSING.value
        await db.commit()

        try:
            image_bytes = await storage.download(task.input_image_path)

            analysis_result = await pipeline.execute(
                mode=AnalysisMode(task.mode),
                image_bytes=image_bytes,
                user_id=str(task.user_id),
                task_id=str(task.id),
            )

            task.result = analysis_result
            task.share_card_path = analysis_result.get("share", {}).get("card_url")
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.now(timezone.utc)

            logger.info("Task %s completed", task_id)

        except Exception as e:
            logger.exception("Task %s failed", task_id)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)[:500]

        await db.commit()


class WorkerSettings:
    functions = [process_analysis]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 120
