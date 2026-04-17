"""Integration tests for the process_analysis worker job (all external providers mocked)."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.enums import TaskStatus
from src.workers.tasks import process_analysis, worker_heartbeat


def _jpeg_stub() -> bytes:
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
        b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
        b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x08\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9"
    )


class _FakeTask:
    """Minimal Task stand-in for mocked DB queries."""

    def __init__(self, task_id, user_id, mode="rating", context=None):
        self.id = task_id
        self.user_id = user_id
        self.mode = mode
        self.status = TaskStatus.PENDING.value
        self.input_image_path = f"inputs/{user_id}/{task_id}.jpg"
        self.context = context or {}
        self.result = None
        self.error_message = None
        self.share_card_path = None
        self.completed_at = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class _FakeUser:
    def __init__(self, user_id, credits=5):
        self.id = user_id
        self.image_credits = credits
        self.username = "testuser"
        self.is_premium = False


def _build_ctx(task, user, *, pipeline_result=None):
    """Build a minimal ARQ ctx dict with mocked dependencies."""
    task_id = str(task.id)
    user_id = task.user_id
    image_b64 = base64.b64encode(_jpeg_stub()).decode("ascii")

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=image_b64)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.publish = AsyncMock()

    db_session = AsyncMock()

    task_result = MagicMock()
    task_result.scalar_one_or_none.return_value = task
    task_result.scalar_one.return_value = task

    user_result = MagicMock()
    user_result.scalar_one.return_value = user
    user_result.scalar_one_or_none.return_value = user

    call_count = [0]

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return task_result
        return user_result

    db_session.execute = AsyncMock(side_effect=_execute_side_effect)
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock()
    db_session.add = MagicMock()

    sessionmaker = MagicMock()
    sessionmaker.return_value.__aenter__ = AsyncMock(return_value=db_session)
    sessionmaker.return_value.__aexit__ = AsyncMock(return_value=False)

    pipeline = AsyncMock()
    pipeline.execute = AsyncMock(return_value=pipeline_result or {
        "score": 7.5,
        "generated_image_url": f"http://test/storage/generated/{user_id}/{task_id}.jpg",
    })

    storage = MagicMock()
    storage.download = AsyncMock(return_value=_jpeg_stub())
    storage.delete = AsyncMock()

    arq = AsyncMock()
    arq.enqueue_job = AsyncMock()

    engine = AsyncMock()
    engine.dispose = AsyncMock()

    ctx = {
        "db_sessionmaker": sessionmaker,
        "redis": redis,
        "pipeline": pipeline,
        "storage": storage,
        "arq": arq,
        "engine": engine,
        "llm": MagicMock(close=AsyncMock()),
        "image_gen": MagicMock(close=AsyncMock()),
    }
    return ctx, db_session


@pytest.mark.asyncio
async def test_process_analysis_completes_task():
    """Verify happy path: task transitions to COMPLETED with result."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(task_id, user_id, context={"credit_pre_reserved": True})
    user = _FakeUser(user_id)

    ctx, db = _build_ctx(task, user)
    await process_analysis(ctx, str(task_id))

    assert task.status == TaskStatus.COMPLETED.value
    assert task.result is not None
    assert task.result.get("has_generated_image") is True
    assert task.completed_at is not None
    ctx["pipeline"].execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_analysis_no_credits_skip_gen():
    """When skip_image_gen, task should complete without image."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(task_id, user_id, context={"skip_image_gen": True})
    user = _FakeUser(user_id, credits=0)

    result = {"score": 6.0}
    ctx, db = _build_ctx(task, user, pipeline_result=result)
    await process_analysis(ctx, str(task_id))

    assert task.status == TaskStatus.COMPLETED.value
    assert task.result.get("has_generated_image") is False
    assert task.result.get("no_image_reason") == "no_credits"


@pytest.mark.asyncio
async def test_process_analysis_failure_refunds_credit():
    """On pipeline failure with pre-reserved credit, credit should be refunded."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(task_id, user_id, context={"credit_pre_reserved": True})
    user = _FakeUser(user_id, credits=4)
    initial_credits = user.image_credits

    ctx, db = _build_ctx(task, user)
    ctx["pipeline"].execute = AsyncMock(side_effect=ValueError("No face detected"))

    await process_analysis(ctx, str(task_id))

    assert task.status == TaskStatus.FAILED.value
    assert "No face detected" in task.error_message
    assert user.image_credits == initial_credits + 1


@pytest.mark.asyncio
async def test_process_analysis_publishes_done_event():
    """Verify Redis pub/sub notification on completion."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(task_id, user_id, context={"credit_pre_reserved": True})
    user = _FakeUser(user_id)

    ctx, db = _build_ctx(task, user)
    await process_analysis(ctx, str(task_id))

    redis = ctx["redis"]
    redis.publish.assert_any_call(f"ratemeai:task_done:{task_id}", "completed")


@pytest.mark.asyncio
async def test_process_analysis_stages_image_in_redis():
    """Generated image should be staged in Redis cache."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(task_id, user_id, context={"credit_pre_reserved": True})
    user = _FakeUser(user_id)

    ctx, db = _build_ctx(task, user)
    await process_analysis(ctx, str(task_id))

    redis = ctx["redis"]
    set_calls = [c for c in redis.set.call_args_list if "gen_image" in str(c)]
    assert len(set_calls) > 0


@pytest.mark.asyncio
async def test_worker_heartbeat():
    """Heartbeat should set the Redis key."""
    redis = AsyncMock()
    redis.set = AsyncMock()
    ctx = {"redis": redis}
    await worker_heartbeat(ctx)
    redis.set.assert_awaited_once()
    args = redis.set.call_args
    assert "ratemeai:worker:heartbeat" in str(args)


@pytest.mark.asyncio
async def test_process_analysis_enqueues_deferred_delta_scoring():
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(task_id, user_id, context={"credit_pre_reserved": True, "defer_delta_scoring": True})
    user = _FakeUser(user_id)

    result = {
        "score": 7.9,
        "generated_image_url": f"http://test/storage/generated/{user_id}/{task_id}.jpg",
        "delta_status": "pending",
    }
    ctx, _db = _build_ctx(task, user, pipeline_result=result)
    await process_analysis(ctx, str(task_id))

    ctx["arq"].enqueue_job.assert_awaited_once_with("compute_delta_scores", str(task_id))


@pytest.mark.asyncio
async def test_process_analysis_cleans_ephemeral_artifacts_when_policy_requires():
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _FakeTask(
        task_id,
        user_id,
        context={
            "credit_pre_reserved": True,
            "policy_flags": {"delete_after_process": True},
        },
    )
    user = _FakeUser(user_id)

    ctx, _db = _build_ctx(task, user)
    await process_analysis(ctx, str(task_id))

    ctx["storage"].delete.assert_any_await(task.input_image_path)
    ctx["storage"].delete.assert_any_await(f"generated/{user_id}/{task_id}.jpg")
