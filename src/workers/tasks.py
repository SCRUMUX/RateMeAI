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
from src.services.task_contract import (
    get_market_id,
    get_policy_flags,
    should_delete_after_process,
)
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
    # Unwrap PipelineStageError so we classify against the *real* cause
    # (a ReadTimeout wrapped as [stage=analyze] is still transient).
    from src.orchestrator.pipeline import PipelineStageError
    if isinstance(exc, PipelineStageError):
        real = exc.original
    else:
        real = exc
    msg = str(real).lower()
    if isinstance(real, (TimeoutError, ConnectionError, OSError)):
        return True
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def _format_task_error(exc: Exception) -> str:
    """Build a structured `error_message` like ``[stage=analyze] ReadTimeout: ...``.

    Truncated to 500 chars (DB column limit).  The stage helps ops pinpoint
    *where* in the pipeline a task died without reading full tracebacks.
    """
    from src.orchestrator.pipeline import PipelineStageError
    if isinstance(exc, PipelineStageError):
        original = exc.original
        stage = exc.stage
    else:
        original = exc
        stage = "worker"
    text = f"[stage={stage}] {type(original).__name__}: {str(original)[:380]}"
    return text[:500]


def _mediapipe_selfcheck() -> None:
    """Probe MediaPipe at worker startup; write a clear log line either way.

    This is observability-only: we do not raise or fail startup. The goal
    is for ops to immediately see in Railway logs whether the native
    MediaPipe wheel loaded successfully in this container (common failure
    mode: ``mediapipe`` imports but the native .so misses ``libGL`` /
    ``libEGL`` on slim images). If this warns, ``analyze_input_quality``
    will degrade into a fail-soft mode (see B2) instead of hard-blocking
    every user with NO_FACE.
    """
    try:
        import io as _io
        from PIL import Image as _Image
        _buf = _io.BytesIO()
        _Image.new("RGB", (64, 64), color=(128, 128, 128)).save(_buf, format="JPEG")
        probe = _buf.getvalue()

        from src.services.identity import IdentityService
        svc = IdentityService()
        svc.detect_face(probe)
    except Exception:
        logger.warning(
            "MediaPipe FaceDetection probe FAILED at worker startup — "
            "face-presence gate will degrade (fail-soft). "
            "Identity preservation itself is unaffected (handled by VLM).",
            exc_info=True,
        )
        return

    from src.services.identity import _mp_available as _id_available
    from src.services.input_quality import _get_mp_detector
    _get_mp_detector()
    from src.services.input_quality import _mp_available as _iq_available

    if _id_available and _iq_available:
        logger.info("MediaPipe FaceDetection available (identity + input_quality)")
    else:
        logger.warning(
            "MediaPipe FaceDetection UNAVAILABLE at worker startup — "
            "NO_FACE gate will degrade (fail-soft). identity=%s input_quality=%s",
            _id_available, _iq_available,
        )


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

    # Privacy note: identity is now verified by the quality-gate VLM (see
    # services/quality_gates.py), not by a local face detector. We still log
    # whether the lightweight MediaPipe face-presence check is available so
    # ops can spot a misconfigured image — a missing detector is a *soft*
    # warning, not a blocker for task processing.
    _mediapipe_selfcheck()
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
    # Privacy: the Redis stash that carried the sanitized input bytes is
    # always disposed, regardless of legacy retention policy.
    for cache_key in task_input_cache_keys(str(task.id), market_id):
        try:
            await redis.delete(cache_key)
        except Exception:
            logger.debug("Failed to delete input cache key %s", cache_key, exc_info=True)

    # Privacy: original image must never remain in storage after processing.
    # For legacy tasks that still have a storage key attached, we purge it
    # here unconditionally. New tasks are created with input_image_path=None.
    if task.input_image_path:
        await _delete_storage_key(storage, task.input_image_path)

    # The generated result honours the legacy `delete_after_process` flag
    # (edge/worker synchronous flow). For the regular primary flow the
    # generated image lives for 72h and is GC'd by `privacy_gc_cron`.
    if include_generated and should_delete_after_process(task.context):
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
                if not task.input_image_path:
                    # Privacy mode: sanitized bytes live only in Redis. If the
                    # stash expired or the worker was restarted past the 15-min
                    # TTL, we cannot recover the input — fail cleanly instead
                    # of crashing on storage.download(None).
                    raise RuntimeError(
                        "Task input stash expired and no legacy storage key "
                        "is available (privacy retention policy). Task must "
                        "be re-submitted by the user."
                    )
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
            policy_flags = get_policy_flags(context)
            allow_pipeline_retry = not bool(policy_flags.get("single_provider_call"))
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
                    if attempt < _MAX_PIPELINE_RETRIES and allow_pipeline_retry and _is_transient(exc):
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

                # Credit was pre-reserved at request time (check_credits декрементирует
                # image_credits сразу). Задача дошла до COMPLETED, но картинки нет —
                # возвращаем кредит здесь, чтобы пользователь не терял его на сбое
                # провайдера / модерации. Без этого рефанда web / bot / edge уходят с
                # «completed + no image» и кредит оставался бы списанным.
                if (
                    credit_pre_reserved
                    and not context.get("skip_image_gen")
                    and not analysis_result.get("credit_refunded")
                ):
                    try:
                        u_ref = await db.execute(
                            select(User).where(User.id == task.user_id).with_for_update()
                        )
                        user_ref = u_ref.scalar_one()
                        user_ref.image_credits += 1
                        db.add(CreditTransaction(
                            user_id=task.user_id,
                            amount=1,
                            balance_after=user_ref.image_credits,
                            tx_type="refund_no_image",
                        ))
                        analysis_result["credit_refunded"] = True
                        analysis_result["credit_deducted"] = False
                        logger.info(
                            "Refunded 1 image credit for completed-without-image task %s (reason=%s)",
                            task_id, analysis_result.get("no_image_reason", "unknown"),
                        )
                    except Exception:
                        logger.exception(
                            "Failed to refund credit for completed-without-image task %s",
                            task_id,
                        )

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
            task.error_message = _format_task_error(e)
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
            # Privacy: the original image is intentionally gone by this point.
            # DeltaScorer works purely off the generated image (downloaded
            # from storage inside compute()) and pre-scores already captured
            # in task_result. Authenticity is derived from the quality
            # report produced earlier by the stateless VLM check — no
            # biometric feature vectors are ever read/written here.
            from src.services.ai_transfer_guard import task_context_scope
            with task_context_scope(task.context):
                await pipeline._delta_scorer.compute(mode, task_result, str(task.user_id), task_id)
                # Persist personal-best perception record now — the main
                # pipeline skipped it because scores were still pre-gen at
                # the time of `_finalize`. After DeltaScorer.compute the
                # perception_scores map holds post-gen values, which is
                # what gamification should track.
                await pipeline._persist_perception_scores(mode, task_result, str(task.user_id))
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


async def privacy_gc_cron(ctx: dict):
    """Physical deletion of generated images + share cards after 72h retention.

    Selects tasks whose ``completed_at`` is older than the configured
    retention window (default 72h), deletes their generated/share storage
    keys, clears the corresponding Redis cache, and zeroes out the URLs in
    ``task.result``. The task row itself (scores, before/after perception)
    is preserved for the user's gallery; a ``_purged_at`` marker lets the
    frontend show "the generated image is no longer available".
    """
    from datetime import timedelta
    from sqlalchemy import select as sa_select

    db_sessionmaker = ctx["db_sessionmaker"]
    storage = ctx["storage"]
    redis = ctx["redis"]

    retention = settings.privacy_result_retention_seconds
    threshold = datetime.now(timezone.utc) - timedelta(seconds=retention)

    try:
        async with db_sessionmaker() as db:
            rows = await db.execute(
                sa_select(Task)
                .where(
                    Task.status == TaskStatus.COMPLETED.value,
                    Task.completed_at.is_not(None),
                    Task.completed_at < threshold,
                )
                .limit(500)
            )
            purged = 0
            for task in rows.scalars().all():
                result = dict(task.result or {})
                if result.get("_purged_at"):
                    continue
                market_id = get_market_id(task.context, fallback=settings.resolved_market_id)

                await _delete_storage_key(storage, f"generated/{task.user_id}/{task.id}.jpg")
                if task.share_card_path:
                    await _delete_storage_key(storage, task.share_card_path)

                for cache_key in gen_image_cache_keys(str(task.id), market_id):
                    try:
                        await redis.delete(cache_key)
                    except Exception:
                        logger.debug("privacy_gc: redis delete failed", exc_info=True)

                result.pop("generated_image_url", None)
                result.pop("generated_image_b64", None)
                result["_purged_at"] = datetime.now(timezone.utc).isoformat()
                task.result = result
                task.share_card_path = None
                if task.input_image_path:
                    await _delete_storage_key(storage, task.input_image_path)
                    task.input_image_path = None
                purged += 1

            if purged:
                await db.commit()
                logger.info("privacy_gc: purged %d task(s)", purged)
    except Exception:
        logger.exception("privacy_gc_cron failed")


class WorkerSettings:
    functions = [process_analysis, compute_delta_scores]
    cron_jobs = [
        cron(reconcile_stuck_tasks_cron, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(worker_heartbeat, second={0, 30}),
        cron(privacy_gc_cron, minute={0, 30}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    # 300s budget: preprocess (~1s) + LLM analyze (up to ~96s worst case
    # with OpenRouter retries after B1) + planner (~0s) + 2-3 Reve steps
    # (~60-90s total) + VLM compare_images quality gate (~10-20s) +
    # finalize. Previous 200s was tight enough to kill borderline jobs
    # before they reached Reve, leaving tasks in PROCESSING state until
    # the 10-min reconciler cleaned them up.
    job_timeout = 300
