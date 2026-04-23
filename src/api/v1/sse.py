"""Server-Sent Events endpoint for real-time task progress updates.

Web / mini-app clients can subscribe to SSE instead of polling.
Supports short-lived SSE tickets to avoid exposing long-lived session
tokens in query strings (which appear in logs and proxy caches).
"""

from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.api.deps import get_db, get_auth_user
from src.models.db import Task, User
from src.services.sessions import resolve_session

logger = logging.getLogger(__name__)
router = APIRouter()

_SSE_TICKET_TTL = 60
_SSE_TICKET_PREFIX = "ratemeai:sse_ticket:"


@router.post("/ticket")
async def create_sse_ticket(
    request: Request,
    user: User = Depends(get_auth_user),
):
    """Issue a short-lived SSE ticket (60s) so the client does not need to
    put the long-lived session token in the EventSource query string."""
    redis = request.app.state.redis
    ticket = secrets.token_urlsafe(32)
    await redis.set(f"{_SSE_TICKET_PREFIX}{ticket}", str(user.id), ex=_SSE_TICKET_TTL)
    return {"ticket": ticket, "ttl": _SSE_TICKET_TTL}


async def _resolve_sse_user(
    request: Request,
    token: str | None = Query(None, description="Bearer token (legacy, prefer ticket)"),
    ticket: str | None = Query(
        None, description="Short-lived SSE ticket from POST /sse/ticket"
    ),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve user from Authorization header, SSE ticket, or legacy query ?token=."""
    redis = request.app.state.redis

    if ticket:
        user_id_str = await redis.get(f"{_SSE_TICKET_PREFIX}{ticket}")
        if user_id_str:
            await redis.delete(f"{_SSE_TICKET_PREFIX}{ticket}")
            user = await db.get(User, user_id_str)
            if user is not None:
                return user
        raise HTTPException(status_code=401, detail="Invalid or expired SSE ticket")

    auth_header = request.headers.get("authorization")
    bearer_token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()
    if not bearer_token and token:
        bearer_token = token.strip()
    if not bearer_token:
        raise HTTPException(status_code=401, detail="Missing auth token")

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
            iter(['data: {"error": "task_not_found"}\n\n']),
            media_type="text/event-stream",
            status_code=404,
        )

    redis = request.app.state.redis
    progress_channel = f"ratemeai:progress:{task_id}"
    done_channel = f"ratemeai:task_done:{task_id}"

    async def event_generator():
        if task.status == "completed":
            yield "event: done\ndata: completed\n\n"
            return
        if task.status == "failed":
            yield "event: done\ndata: failed\n\n"
            return

        pubsub = redis.pubsub()
        await pubsub.subscribe(progress_channel, done_channel)

        # Fallback poll каждые _DB_POLL_INTERVAL секунд — против потерянных pubsub-сообщений.
        # Используем select() + отдельный refresh, чтобы SQLAlchemy не отдавал закешированный объект.
        _DB_POLL_INTERVAL = 15.0
        last_db_poll = 0.0

        async def _fetch_status() -> str | None:
            try:
                res = await db.execute(select(Task.status).where(Task.id == task.id))
                return res.scalar_one_or_none()
            except Exception:
                logger.debug("SSE status refetch failed", exc_info=True)
                return None

        try:
            loop = asyncio.get_running_loop()
            while True:
                if await request.is_disconnected():
                    break

                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
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
                    continue

                # Нет сообщения → heartbeat. Раз в _DB_POLL_INTERVAL сек страхуемся
                # повторным чтением статуса из БД, чтобы поймать пропущенный pubsub.
                now = loop.time()
                if now - last_db_poll >= _DB_POLL_INTERVAL:
                    last_db_poll = now
                    status = await _fetch_status()
                    if status in {"completed", "failed"}:
                        yield f"event: done\ndata: {status}\n\n"
                        break
                yield ": heartbeat\n\n"
                await asyncio.sleep(2)
        finally:
            try:
                await pubsub.unsubscribe(progress_channel, done_channel)
            except Exception:
                logger.debug("SSE pubsub unsubscribe failed", exc_info=True)
            try:
                await pubsub.close()
            except Exception:
                logger.debug("SSE pubsub close failed", exc_info=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
