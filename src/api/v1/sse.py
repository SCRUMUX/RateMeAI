"""Server-Sent Events endpoint for real-time task progress updates.

Web / mini-app clients can subscribe to SSE instead of polling.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.api.deps import get_auth_user, get_db
from src.models.db import Task, User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/progress")
async def task_progress_stream(
    request: Request,
    task_id: str = Query(..., description="Task ID to subscribe to"),
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE stream of task progress and completion events.

    Subscribes to Redis PubSub channels:
    - ``ratemeai:progress:<task_id>`` for step-level progress
    - ``ratemeai:task_done:<task_id>`` for completion/failure signal
    """
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None or task.user_id != user.id:
        return StreamingResponse(
            iter(["data: {\"error\": \"task_not_found\"}\n\n"]),
            media_type="text/event-stream",
            status_code=404,
        )

    redis = request.app.state.redis
    progress_channel = f"ratemeai:progress:{task_id}"
    done_channel = f"ratemeai:task_done:{task_id}"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(progress_channel, done_channel)
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    channel = msg["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    if channel == done_channel:
                        yield f"event: done\ndata: {data}\n\n"
                        break
                    else:
                        yield f"event: progress\ndata: {data}\n\n"
                else:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(2)
        finally:
            await pubsub.unsubscribe(progress_channel, done_channel)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
