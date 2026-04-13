"""Server-Sent Events endpoint for real-time task progress updates.

Web / mini-app clients can subscribe to SSE instead of polling.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.api.deps import get_db
from src.models.db import Task, User
from src.services.sessions import resolve_session

logger = logging.getLogger(__name__)
router = APIRouter()


async def _resolve_sse_user(
    request: Request,
    token: str | None = Query(None, description="Bearer token (for EventSource which cannot set headers)"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve user from Authorization header or query ?token= (SSE compat)."""
    auth_header = request.headers.get("authorization")
    bearer_token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()
    if not bearer_token and token:
        bearer_token = token.strip()
    if not bearer_token:
        raise HTTPException(status_code=401, detail="Missing auth token")

    redis = request.app.state.redis
    user_id = await resolve_session(redis, bearer_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/progress")
async def task_progress_stream(
    request: Request,
    task_id: str = Query(..., description="Task ID to subscribe to"),
    user: User = Depends(_resolve_sse_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE stream of task progress and completion events.

    Subscribes to Redis PubSub channels:
    - ``ratemeai:progress:<task_id>`` for step-level progress
    - ``ratemeai:task_done:<task_id>`` for completion/failure signal

    Auth: accepts Authorization header or ``?token=`` query param
    (EventSource API cannot set custom headers).
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
