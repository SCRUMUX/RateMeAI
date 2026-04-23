from __future__ import annotations

import base64
import logging
import uuid

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, User, CreditTransaction
from src.models.enums import AnalysisMode, TaskStatus
from src.models.schemas import TaskCreated
from src.api.deps import get_db, get_redis, check_credits_with_consent
from src.providers.factory import get_storage
from src.services.consent import (
    CONSENT_AI_TRANSFER,
    CONSENT_DATA_PROCESSING,
    snapshot_for_task,
)
from src.services.privacy import PrivacyLayer
from src.services.task_contract import (
    build_policy_flags,
    build_task_context,
    get_market_id,
    get_policy_flags,
    get_scenario_slug,
    get_scenario_type,
    get_trace_id,
)
from src.utils.redis_keys import gen_image_cache_key
from prometheus_client import Counter

ANALYZE_REQUESTS = Counter(
    "ratemeai_analyze_requests_total",
    "Total POST /analyze requests (task creation attempts)",
    labelnames=["mode", "has_style", "has_enhancement_level"],
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy fallback pool used only when running outside a FastAPI lifespan
# (e.g. unit tests, one-off scripts). In production ``app.state.arq_pool``
# is always provisioned in ``src/main.py`` lifespan and takes precedence.
_arq_pool: ArqRedis | None = None


async def _get_arq(app=None) -> ArqRedis:
    global _arq_pool
    if app is not None:
        pool = getattr(app.state, "arq_pool", None)
        if pool is not None:
            return pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def _handle_edge_analysis(
    app_state,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    image_bytes: bytes,
    mode: str,
    style: str,
    profession: str,
    enhancement_level: int,
    pre_analysis_id: str,
    variant_id: str,
    scenario_slug: str,
    scenario_type: str,
    entry_mode: str,
    image_model: str = "",
    image_quality: str = "",
) -> None:
    """In edge mode: proxy the AI task to the primary Railway backend.

    Runs as a background coroutine with its own DB session (the request session
    is already closed by the time long-running remote polling finishes).
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from src.services.remote_ai import get_remote_ai, RemoteAIError

    db_sessionmaker = app_state.db_sessionmaker
    redis: Redis = app_state.redis

    try:
        remote_ai = get_remote_ai()
    except Exception as exc:
        logger.exception("Edge handler: cannot init RemoteAI for task %s", task_id)
        await _fail_edge_task(db_sessionmaker, redis, task_id, user_id, f"Edge config error: {exc}")
        return

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    task_context: dict | None = None
    market_id = settings.resolved_market_id
    try:
        async with db_sessionmaker() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                logger.error("Edge handler: task %s not found", task_id)
                return

            task.status = TaskStatus.PROCESSING.value
            task_context = task.context
            market_id = get_market_id(task_context, fallback=settings.resolved_market_id)
            await db.commit()

        async def _edge_progress(status: str, poll_count: int) -> None:
            try:
                estimated_total = 45
                current = min(poll_count * 2, estimated_total - 1)
                await redis.publish(
                    f"ratemeai:progress:{task_id}",
                    f"{status}:{current}:{estimated_total}",
                )
            except Exception:
                pass

        try:
            result_data = await remote_ai.submit_and_wait(
                image_b64=image_b64,
                mode=mode,
                style=style,
                profession=profession,
                enhancement_level=enhancement_level,
                pre_analysis_id=pre_analysis_id,
                variant_id=variant_id,
                edge_task_id=str(task_id),
                market_id=market_id,
                scenario_slug=get_scenario_slug(task_context) or "",
                scenario_type=get_scenario_type(task_context) or "",
                entry_mode=(task_context or {}).get("entry_mode", ""),
                trace_id=get_trace_id(task_context) or str(task_id),
                policy_flags=get_policy_flags(task_context),
                artifact_refs=(task_context or {}).get("artifact_refs") or {},
                # v1.22: forward A/B selection to the primary so the
                # executor engages Nano Banana 2 / GPT Image 2 instead
                # of silently falling through to the legacy StyleRouter.
                image_model=(task_context or {}).get("image_model", "") or image_model,
                image_quality=(task_context or {}).get("image_quality", "") or image_quality,
                on_poll=_edge_progress,
            )

            remote_result = result_data.get("result") or {}
            gen_b64 = result_data.get("generated_image_b64")

            if gen_b64:
                gen_key = f"generated/{user_id}/{task_id}.jpg"
                storage = get_storage()
                await storage.upload(gen_key, base64.b64decode(gen_b64))

                await redis.set(
                    gen_image_cache_key(str(task_id), market_id),
                    gen_b64,
                    ex=settings.gen_image_redis_ttl_seconds,
                )

                remote_result["generated_image_url"] = (
                    f"{settings.api_base_url.rstrip('/')}/storage/{gen_key}"
                )
                remote_result.pop("generated_image_b64", None)
            else:
                remote_result.pop("generated_image_url", None)
                remote_result.pop("image_url", None)
                remote_result.pop("generated_image_b64", None)
                if not remote_result.get("no_image_reason"):
                    has_gen = remote_result.get("has_generated_image", False)
                    if has_gen:
                        logger.warning(
                            "Task %s: primary reported has_generated_image=True "
                            "but b64 was not returned; marking as generation_error",
                            task_id,
                        )
                        remote_result["no_image_reason"] = "generation_error"
                        remote_result["has_generated_image"] = False

            credit_pre_reserved = (task_context or {}).get("credit_pre_reserved", False)
            remote_result["credit_deducted"] = credit_pre_reserved

            async with db_sessionmaker() as db:
                from src.models.db import UsageLog
                from datetime import date as _date
                today = _date.today()
                usage_row = await db.execute(
                    select(UsageLog).where(
                        UsageLog.user_id == user_id,
                        UsageLog.usage_date == today,
                    )
                )
                usage_log = usage_row.scalar_one_or_none()
                if usage_log:
                    usage_log.count += 1
                else:
                    db.add(UsageLog(user_id=user_id, usage_date=today, count=1))

                result_row = await db.execute(select(Task).where(Task.id == task_id))
                task_obj = result_row.scalar_one()
                task_obj.result = remote_result
                task_obj.status = TaskStatus.COMPLETED.value
                task_obj.completed_at = datetime.now(timezone.utc)
                await db.commit()

            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "completed")
            except Exception:
                pass

        except Exception as exc:
            is_remote = isinstance(exc, RemoteAIError)
            if is_remote:
                logger.error("Edge AI proxy failed for task %s: %s", task_id, exc)
            else:
                logger.exception("Unexpected edge handler error for task %s", task_id)

            async with db_sessionmaker() as db:
                result_row = await db.execute(select(Task).where(Task.id == task_id))
                task_obj = result_row.scalar_one_or_none()
                if task_obj and task_obj.status not in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
                    task_obj.status = TaskStatus.FAILED.value
                    task_obj.error_message = (str(exc) if is_remote else f"Edge proxy error: {exc}")[:500]

                    credit_pre_reserved = (task_context or {}).get("credit_pre_reserved", False)
                    if credit_pre_reserved:
                        u = await db.execute(
                            select(User).where(User.id == user_id).with_for_update()
                        )
                        fresh_user = u.scalar_one_or_none()
                        if fresh_user:
                            fresh_user.image_credits += 1
                            db.add(CreditTransaction(
                                user_id=user_id,
                                amount=1,
                                balance_after=fresh_user.image_credits,
                                tx_type="refund_failed_task",
                            ))
                            logger.info("Refunded 1 credit to user %s for failed edge task %s", user_id, task_id)

                    await db.commit()
            try:
                await redis.publish(f"ratemeai:task_done:{task_id}", "failed")
            except Exception:
                pass

    except Exception as exc:
        logger.exception("FATAL: unhandled error in edge handler for task %s", task_id)
        await _fail_edge_task(db_sessionmaker, redis, task_id, user_id, f"Internal edge error: {exc}")


async def _fail_edge_task(db_sessionmaker, redis, task_id, user_id, error_msg: str) -> None:
    """Mark a task as failed from outside the main DB session (crash recovery)."""
    from sqlalchemy import select
    try:
        async with db_sessionmaker() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            updated = False
            if task and task.status not in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
                task.status = TaskStatus.FAILED.value
                task.error_message = error_msg[:500]

                credit_pre_reserved = (task.context or {}).get("credit_pre_reserved", False)
                if credit_pre_reserved:
                    u = await db.execute(
                        select(User).where(User.id == user_id).with_for_update()
                    )
                    fresh_user = u.scalar_one_or_none()
                    if fresh_user:
                        fresh_user.image_credits += 1
                        db.add(CreditTransaction(
                            user_id=user_id,
                            amount=1,
                            balance_after=fresh_user.image_credits,
                            tx_type="refund_failed_task",
                        ))

                await db.commit()
                updated = True
            if updated:
                try:
                    await redis.publish(f"ratemeai:task_done:{task_id}", "failed")
                except Exception:
                    pass
    except Exception:
        logger.exception("FATAL: failed to mark task %s as failed in crash recovery", task_id)


AB_MODELS_ALLOWED = frozenset({"nano_banana_2", "gpt_image_2"})
AB_QUALITIES_ALLOWED = frozenset({"low", "medium", "high"})


@router.post("", response_model=TaskCreated, status_code=202)
async def create_analysis(
    request: Request,
    image: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.RATING),
    style: str = Form(""),
    profession: str = Form(""),
    enhancement_level: int = Form(0),
    pre_analysis_id: str = Form(""),
    variant_id: str = Form(""),
    scenario_slug: str = Form(""),
    scenario_type: str = Form(""),
    entry_mode: str = Form(""),
    image_model: str = Form(""),
    image_quality: str = Form(""),
    framing: str = Form(""),
    input_hints: str = Form(""),
    user: User = Depends(check_credits_with_consent),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    ANALYZE_REQUESTS.labels(
        mode=mode.value,
        has_style=str(bool(style.strip())).lower(),
        has_enhancement_level=str(enhancement_level > 0).lower(),
    ).inc()

    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    raw_bytes = await image.read()
    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    # Privacy layer: strip EXIF, normalize, discard raw bytes immediately.
    # The sanitized image is the only representation that flows onward.
    privacy = PrivacyLayer(redis=redis)
    try:
        sanitized = privacy.sanitize_and_normalize(raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        raw_bytes = b""  # noqa: F841 — explicit drop reference for GC
    image_bytes = sanitized.bytes_

    task_uuid = uuid.uuid4()

    ctx: dict = {}
    if style.strip():
        ctx["style"] = style.strip()
    if profession.strip():
        ctx["profession"] = profession.strip()
    if enhancement_level > 0:
        ctx["enhancement_level"] = enhancement_level
    if pre_analysis_id.strip():
        ctx["pre_analysis_id"] = pre_analysis_id.strip()
    if variant_id.strip():
        ctx["variant_id"] = variant_id.strip()
    if framing.strip():
        ctx["framing"] = framing.strip()
    if input_hints.strip():
        import json
        try:
            ctx["input_hints"] = json.loads(input_hints.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse input_hints JSON: %s", input_hints)
    if getattr(user, "_credit_reserved", False):
        ctx["credit_pre_reserved"] = True
    if mode in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL):
        ctx["defer_delta_scoring"] = True

    # v1.22: A/B path is now the default. If the client did not send
    # ``image_model`` (old bot build, edge proxy, curl, etc.) we fall
    # back to ``settings.ab_default_model`` / ``settings.ab_default_quality``
    # so the executor always routes through the new providers. The old
    # hybrid StyleRouter only takes over when ``AB_TEST_ENABLED=false``
    # is flipped on Railway — that's the documented emergency rollback
    # and keeps this endpoint one env-var away from pre-v1.22 behaviour.
    if settings.ab_test_enabled:
        im = (image_model or "").strip().lower()
        iq = (image_quality or "").strip().lower()
        if im not in AB_MODELS_ALLOWED:
            im = getattr(settings, "ab_default_model", "gpt_image_2")
            if im not in AB_MODELS_ALLOWED:
                im = "gpt_image_2"
        if iq not in AB_QUALITIES_ALLOWED:
            iq = getattr(settings, "ab_default_quality", "low")
            if iq not in AB_QUALITIES_ALLOWED:
                iq = "low"
        ctx["image_model"] = im
        ctx["image_quality"] = iq

    consent_snapshot = getattr(user, "_consents_snapshot", None) or {}
    if consent_snapshot:
        ctx["consent"] = snapshot_for_task(consent_snapshot)

    trace_id = request.headers.get("x-trace-id") or str(task_uuid)
    policy_flags = build_policy_flags(
        cache_allowed=not settings.uses_remote_ai,
        delete_after_process=True,
        retention_policy="privacy_72h",
        data_class="user_photo",
        single_provider_call=True,
        consent_data_processing=CONSENT_DATA_PROCESSING in consent_snapshot,
        consent_ai_transfer=CONSENT_AI_TRANSFER in consent_snapshot,
    )
    ctx = build_task_context(
        ctx,
        market_id=settings.resolved_market_id,
        service_role=settings.resolved_service_role,
        compute_mode=settings.resolved_compute_mode,
        scenario_slug=scenario_slug,
        scenario_type=scenario_type,
        entry_mode=entry_mode,
        trace_id=trace_id,
        policy_flags=policy_flags,
    )

    task = Task(
        id=task_uuid,
        user_id=user.id,
        mode=mode.value,
        status=TaskStatus.PENDING.value,
        input_image_path=None,
        context=ctx or None,
    )
    db.add(task)

    await db.commit()
    await db.refresh(task)

    credits_remaining = getattr(user, "_credits_remaining", None)
    headers = {}
    if credits_remaining is not None:
        headers["X-Credits-Remaining"] = str(credits_remaining)

    if settings.uses_remote_ai:
        import asyncio

        edge_task = asyncio.create_task(
            _handle_edge_analysis(
                app_state=request.app.state,
                task_id=task.id,
                user_id=user.id,
                image_bytes=image_bytes,
                mode=task.mode,
                style=style.strip(),
                profession=profession.strip(),
                enhancement_level=enhancement_level,
                pre_analysis_id=pre_analysis_id.strip(),
                variant_id=variant_id.strip(),
                scenario_slug=scenario_slug.strip(),
                scenario_type=scenario_type.strip(),
                entry_mode=entry_mode.strip(),
                # v1.22: A/B selection must survive the edge→primary hop.
                # ``ctx["image_model"]`` was already normalized above
                # (unknown/empty → settings.ab_default_model) so we hand
                # the primary an explicit choice rather than an empty
                # string that would land on the legacy StyleRouter.
                image_model=ctx.get("image_model", "") or image_model,
                image_quality=ctx.get("image_quality", "") or image_quality,
            ),
            name=f"edge-analysis-{task.id}",
        )
        # Keep a strong reference so the task cannot be garbage-collected
        # mid-flight (asyncio only holds a weakref) and so lifespan shutdown
        # can drain it. Any unhandled exception is logged — without this
        # callback an error inside _handle_edge_analysis before the task's
        # own try/except would silently disappear.
        edge_tasks: set = getattr(request.app.state, "edge_tasks", None)
        if edge_tasks is not None:
            edge_tasks.add(edge_task)
            edge_task.add_done_callback(edge_tasks.discard)

        def _log_edge_failure(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.exception(
                    "Edge-proxy task %s crashed with unhandled exception",
                    task.id,
                    exc_info=exc,
                )

        edge_task.add_done_callback(_log_edge_failure)
        body = TaskCreated(task_id=task.id, status=TaskStatus.PENDING, estimated_seconds=30)
        return JSONResponse(
            content=body.model_dump(mode="json"),
            status_code=202,
            headers=headers,
        )

    try:
        stash_key = await privacy.stash_for_pipeline(
            sanitized,
            str(task.id),
            settings.resolved_market_id,
        )
    except Exception:
        logger.exception("Privacy stash failed for task %s", task.id)
        raise HTTPException(status_code=500, detail="Failed to stage task input") from None
    if not stash_key:
        raise HTTPException(status_code=500, detail="Failed to stage task input")

    arq = await _get_arq(request.app)
    await arq.enqueue_job("process_analysis", str(task.id))

    body = TaskCreated(task_id=task.id, status=TaskStatus.PENDING, estimated_seconds=15)
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=202,
        headers=headers,
    )
