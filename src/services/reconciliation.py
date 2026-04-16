"""Shared stuck-task reconciliation logic used by both worker cron and edge reconciler."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.db import Task, User, CreditTransaction
from src.models.enums import TaskStatus
from src.metrics import TASKS_RECONCILED, TASKS_FAILED, TASKS_IN_PROCESSING

logger = logging.getLogger(__name__)

STUCK_TASK_THRESHOLD_MINUTES = 10


async def reconcile_stuck_tasks(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    threshold_minutes: int = STUCK_TASK_THRESHOLD_MINUTES,
    source: str = "worker",
    track_processing_gauge: bool = False,
) -> int:
    """Find tasks stuck in PROCESSING beyond the threshold and mark them failed.

    Returns the number of reconciled tasks.
    """
    threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    async with db_sessionmaker() as db:
        if track_processing_gauge:
            all_processing = await db.execute(
                select(Task).where(Task.status == TaskStatus.PROCESSING.value)
            )
            TASKS_IN_PROCESSING.set(len(all_processing.scalars().all()))

        rows = await db.execute(
            select(Task).where(
                Task.status == TaskStatus.PROCESSING.value,
                Task.updated_at < threshold,
            )
        )
        stuck_tasks = rows.scalars().all()

        for task in stuck_tasks:
            task.status = TaskStatus.FAILED.value
            task.error_message = (
                f"Task exceeded {threshold_minutes}min processing SLA "
                f"and was marked failed by {source} reconciler."
            )
            TASKS_RECONCILED.inc()
            TASKS_FAILED.labels(reason="stuck_timeout").inc()
            logger.warning(
                "%s reconciler: task %s stuck since %s, marking failed",
                source.capitalize(), task.id, task.updated_at,
            )

            if (task.context or {}).get("credit_pre_reserved"):
                try:
                    u = await db.execute(
                        select(User).where(User.id == task.user_id).with_for_update()
                    )
                    user = u.scalar_one_or_none()
                    if user:
                        user.image_credits += 1
                        tx_type = "refund_stuck_edge_task" if source == "edge" else "refund_stuck_task"
                        db.add(CreditTransaction(
                            user_id=task.user_id,
                            amount=1,
                            balance_after=user.image_credits,
                            tx_type=tx_type,
                        ))
                        logger.info(
                            "%s reconciler: refunded credit for task %s",
                            source.capitalize(), task.id,
                        )
                    else:
                        logger.error(
                            "%s reconciler: user %s not found for task %s",
                            source.capitalize(), task.user_id, task.id,
                        )
                except Exception:
                    logger.exception(
                        "%s reconciler: failed to refund credit for task %s",
                        source.capitalize(), task.id,
                    )

            try:
                await redis.publish(f"ratemeai:task_done:{task.id}", "failed")
            except Exception:
                pass

        if stuck_tasks:
            await db.commit()
            logger.info(
                "%s reconciler: marked %d stuck tasks as failed",
                source.capitalize(), len(stuck_tasks),
            )

    return len(stuck_tasks)
