"""Server-Sent Events endpoint for real-time task progress updates.

Web / mini-app clients can subscribe to SSE instead of polling.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from src.api.deps import get_auth_user
from src.models.db import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/progress")
async def task_progress_stream(
    request: Request,
    user: User = Depends(get_auth_user),
):
    """SSE stream of task progress and completion events for the authenticated user.

    Subscribes to Redis PubSub channel `ratemeai:progress:<user_id>`.
    Messages are forwarded as SSE events.
    """
    redis = request.app.state.redis
    channel_name = f"ratemeai:progress:{user.id}"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_name)
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
                else:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(2)
        finally:
            await pubsub.unsubscribe(channel_name)
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
