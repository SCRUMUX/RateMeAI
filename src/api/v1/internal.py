"""Internal API for edge→primary AI task proxying.

These endpoints are called by the RU edge server to delegate AI processing
to the primary Railway backend. Protected by INTERNAL_API_KEY.
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task
from src.models.enums import AnalysisMode, TaskStatus
from src.api.deps import get_db, get_redis
from src.services.task_contract import build_policy_flags, build_task_context


def _assert_consent_flags(policy_flags: dict[str, Any]) -> None:
    """Edge→primary must forward both consent flags. Missing → HTTP 451."""
    merged = build_policy_flags(policy_flags or None)
    missing = []
    if not merged.get("consent_data_processing"):
        missing.append("data_processing")
    if not merged.get("consent_ai_transfer"):
        missing.append("ai_transfer")
    if missing:
        raise HTTPException(
            status_code=451,
            detail={"code": "consent_required", "missing": missing},
        )

logger = logging.getLogger(__name__)
router = APIRouter()

_arq_pool: ArqRedis | None = None


async def _get_arq() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def _verify_internal_key(x_internal_key: str = Header(...)) -> str:
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="Internal API not configured")
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    return x_internal_key


@router.get("/ping")
async def internal_ping(_key: str = Depends(_verify_internal_key)):
    """Lightweight auth check for edge→primary connectivity verification."""
    return {"status": "ok"}


# ── Schemas ──

class RemotePreAnalyzeRequest(BaseModel):
    image_b64: str
    mode: AnalysisMode = AnalysisMode.DATING
    profession: str = ""
    skip_validation: bool = False
    market_id: str = "global"
    trace_id: str = ""
    policy_flags: dict[str, Any] = Field(default_factory=dict)


class RemoteAnalysisRequest(BaseModel):
    image_b64: str
    mode: AnalysisMode = AnalysisMode.RATING
    style: str = ""
    profession: str = ""
    enhancement_level: int = 0
    pre_analysis_id: str = ""
    edge_task_id: str = Field("", description="Task ID from the edge server for tracing")
    market_id: str = "global"
    scenario_slug: str = ""
    scenario_type: str = ""
    entry_mode: str = ""
    trace_id: str = ""
    policy_flags: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: dict[str, str] = Field(default_factory=dict)


class RemoteAnalysisResponse(BaseModel):
    remote_task_id: uuid.UUID
    status: str = "pending"


class RemoteTaskStatusResponse(BaseModel):
    status: str
    result: dict | None = None
    error_message: str | None = None
    generated_image_b64: str | None = None


# ── Endpoints ──

@router.post("/process-analysis", response_model=RemoteAnalysisResponse, status_code=202)
async def process_analysis_remote(
    request: RemoteAnalysisRequest,
    _key: str = Depends(_verify_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Accept an AI analysis task from the edge server and enqueue it for processing."""
    _assert_consent_flags(request.policy_flags)

    try:
        image_bytes = base64.b64decode(request.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    # Privacy: sanitize (strip EXIF) immediately; original bytes never leave memory.
    from src.services.privacy import PrivacyLayer

    try:
        sanitized = PrivacyLayer.sanitize_and_normalize(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    image_bytes = sanitized.bytes_

    internal_user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "edge-proxy.internal")

    policy_flags = build_policy_flags(
        request.policy_flags or None,
        cache_allowed=False,
        delete_after_process=True,
        retention_policy="ephemeral",
        data_class="regional_photo",
        single_provider_call=True,
    )
    ctx: dict[str, Any] = {}
    if request.style.strip():
        ctx["style"] = request.style.strip()
    if request.profession.strip():
        ctx["profession"] = request.profession.strip()
    if request.enhancement_level > 0:
        ctx["enhancement_level"] = request.enhancement_level
    if request.pre_analysis_id.strip():
        ctx["pre_analysis_id"] = request.pre_analysis_id.strip()
    if request.edge_task_id:
        ctx["edge_task_id"] = request.edge_task_id

    ctx["skip_credit_deduct"] = True
    ctx["defer_delta_scoring"] = True
    ctx = build_task_context(
        ctx,
        market_id=request.market_id,
        service_role=settings.resolved_service_role,
        compute_mode=settings.resolved_compute_mode,
        scenario_slug=request.scenario_slug,
        scenario_type=request.scenario_type,
        entry_mode=request.entry_mode,
        trace_id=request.trace_id or request.edge_task_id or str(uuid.uuid4()),
        remote_origin="market-proxy",
        policy_flags=policy_flags,
        artifact_refs={**request.artifact_refs} if request.artifact_refs else None,
    )

    task = Task(
        user_id=internal_user_id,
        mode=request.mode.value,
        status=TaskStatus.PENDING.value,
        input_image_path=None,
        context=ctx or None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Privacy: stash sanitized bytes in Redis only (no storage write).
    privacy = PrivacyLayer(redis=redis)
    stash_key = await privacy.stash_for_pipeline(
        sanitized,
        str(task.id),
        request.market_id,
    )
    if not stash_key:
        logger.error("Privacy stash failed for remote task %s", task.id)
        raise HTTPException(status_code=500, detail="Failed to stage task input")

    arq = await _get_arq()
    await arq.enqueue_job("process_analysis", str(task.id))

    logger.info(
        "Accepted remote analysis task %s (edge_task=%s, market=%s, mode=%s, scenario=%s)",
        task.id,
        request.edge_task_id,
        request.market_id,
        request.mode.value,
        request.scenario_type or "n/a",
    )
    return RemoteAnalysisResponse(remote_task_id=task.id, status="pending")


@router.get("/task/{task_id}/status", response_model=RemoteTaskStatusResponse)
async def get_remote_task_status(
    task_id: uuid.UUID,
    _key: str = Depends(_verify_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Poll AI task status. Returns result + generated image as base64 when done."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    response = RemoteTaskStatusResponse(
        status=task.status,
        error_message=task.error_message,
    )

    if task.status == TaskStatus.COMPLETED.value and task.result:
        response.result = task.result

        from src.services.task_contract import get_market_id
        from src.utils.redis_keys import gen_image_cache_keys

        market_id = get_market_id(task.context, fallback=settings.resolved_market_id)
        b64 = None
        for key in gen_image_cache_keys(str(task.id), market_id):
            b64 = await redis.get(key)
            if b64:
                break
        if b64:
            response.generated_image_b64 = b64
        elif task.result.get("generated_image_b64"):
            response.generated_image_b64 = task.result["generated_image_b64"]

    return response


@router.post("/pre-analyze")
async def pre_analyze_remote(
    request: RemotePreAnalyzeRequest,
    _key: str = Depends(_verify_internal_key),
    redis: Redis = Depends(get_redis),
):
    """Run pre-analysis on the primary backend for the edge server."""
    _assert_consent_flags(request.policy_flags)

    try:
        image_bytes = base64.b64decode(request.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    if not request.skip_validation:
        from src.services.privacy import PrivacyLayer
        from src.utils.image import has_face_heuristic

        try:
            sanitized = PrivacyLayer.sanitize_and_normalize(image_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        image_bytes = sanitized.bytes_

        if not has_face_heuristic(image_bytes):
            raise HTTPException(
                status_code=400,
                detail="На фото не обнаружено лицо. Загрузи портретное фото.",
            )

    from src.orchestrator.router import ModeRouter
    from src.providers.factory import get_llm
    from src.prompts.engine import PromptEngine
    from src.utils.humanize import humanize_result_scores
    from src.utils.security import extract_nsfw_from_analysis
    from src.models.schemas import RatingResult
    from src.metrics import LLM_CALLS

    from src.services.ai_transfer_guard import task_context_scope

    llm = get_llm()
    mode_router = ModeRouter(llm, PromptEngine())
    service = mode_router.get_service(request.mode)

    guard_ctx = {"policy_flags": build_policy_flags(request.policy_flags or None)}
    with task_context_scope(guard_ctx):
        if request.mode == AnalysisMode.CV:
            prof = request.profession.strip() or "не указана"
            result = await service.analyze(image_bytes, profession=prof)
        else:
            result = await service.analyze(image_bytes)
    LLM_CALLS.labels(purpose=f"preanalyze_{request.mode.value}").inc()

    raw_dict = result if isinstance(result, dict) else (
        result.model_dump() if hasattr(result, "model_dump") else result
    )

    is_safe, reason = extract_nsfw_from_analysis(raw_dict)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Фото не прошло модерацию: {reason}")

    if isinstance(result, RatingResult):
        result_dict = result.model_dump()
    else:
        result_dict = raw_dict

    pre_id = str(uuid.uuid4())
    humanize_result_scores(result_dict, pre_id)
    result_dict["_scores_humanized"] = True

    from src.api.v1.pre_analyze import _extract_composite_score

    score = _extract_composite_score(request.mode, result_dict)
    perception = result_dict.get("perception_scores", {})
    if hasattr(perception, "model_dump"):
        perception = perception.model_dump()

    insights = result_dict.get("perception_insights", [])
    if insights and hasattr(insights[0], "model_dump"):
        insights = [i.model_dump() for i in insights]

    opportunities = result_dict.get("enhancement_opportunities", [])

    from src.utils.redis_keys import preanalysis_cache_key
    import json as _json

    _PRE_ANALYSIS_TTL = 1800
    try:
        await redis.set(
            preanalysis_cache_key(pre_id, request.market_id),
            _json.dumps(result_dict, default=str),
            ex=_PRE_ANALYSIS_TTL,
        )
    except Exception:
        logger.exception("Failed to cache pre-analysis %s on primary", pre_id)

    return {
        "pre_analysis_id": pre_id,
        "mode": request.mode.value,
        "first_impression": result_dict.get("first_impression", result_dict.get("analysis", "")),
        "score": score,
        "perception_scores": perception,
        "perception_insights": insights,
        "enhancement_opportunities": opportunities,
    }


# ── Diagnostics ──
#
# Read-only, ops-facing view of recent FAILED tasks so we can diagnose
# "why generation died fast" without needing Railway log access. Protected
# by INTERNAL_API_KEY just like the rest of this router.
#
# Only surface-level metadata is returned (no image paths, no user PII):
#   - task_id, mode, status
#   - error_message (already truncated to 500 chars by _format_task_error)
#   - created_at / updated_at and duration_ms
#   - context_keys (keys only, without values — prevents leaking emails,
#     prompts, trace_ids, etc.)
#   - has_input_path / has_result flags
#
# Purpose: pin-point which stage of the pipeline kills the task. Since the
# worker stores errors as "[stage=<stage>] <ExcType>: <msg>", one query
# immediately tells us whether the issue is input_quality, privacy stash,
# moderation, provider, or something else. Required for proper root-cause
# analysis of the 2–3s "Ошибка генерации" report.

_RECENT_ERRORS_DEFAULT_HOURS = 24
_RECENT_ERRORS_MAX_LIMIT = 200


@router.get("/diagnostics/recent-errors")
async def recent_errors(
    limit: int = Query(50, ge=1, le=_RECENT_ERRORS_MAX_LIMIT),
    hours: int = Query(_RECENT_ERRORS_DEFAULT_HOURS, ge=1, le=168),
    _key: str = Depends(_verify_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Return recent FAILED tasks with structured error metadata.

    Safe to call against production: no PII, no task inputs, no tokens.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Task)
        .where(Task.status == TaskStatus.FAILED.value)
        .where(Task.updated_at >= since)
        .order_by(Task.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[dict[str, Any]] = []
    for t in rows:
        created_at = t.created_at
        updated_at = t.updated_at
        duration_ms: int | None = None
        if created_at and updated_at:
            duration_ms = int((updated_at - created_at).total_seconds() * 1000)

        err = t.error_message or ""
        stage: str | None = None
        exc_type: str | None = None
        # Error format from src/workers/tasks.py::_format_task_error:
        #   "[stage=<stage>] <ExcType>: <message>"
        if err.startswith("[stage="):
            try:
                closing = err.index("]")
                stage = err[len("[stage=") : closing]
                tail = err[closing + 1 :].lstrip()
                colon = tail.find(":")
                if colon > 0:
                    exc_type = tail[:colon]
            except ValueError:
                pass

        ctx = t.context or {}
        items.append(
            {
                "task_id": str(t.id),
                "mode": t.mode,
                "stage": stage,
                "exc_type": exc_type,
                "error_message": err,
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "duration_ms": duration_ms,
                "context_keys": sorted(ctx.keys()) if isinstance(ctx, dict) else [],
                "has_input_path": bool(t.input_image_path),
                "has_result": bool(t.result),
                "market_id": (ctx.get("market_id") if isinstance(ctx, dict) else None),
                "scenario_type": (ctx.get("scenario_type") if isinstance(ctx, dict) else None),
                "scenario_slug": (ctx.get("scenario_slug") if isinstance(ctx, dict) else None),
                "style": (ctx.get("style") if isinstance(ctx, dict) else None),
                "skip_image_gen": (ctx.get("skip_image_gen") if isinstance(ctx, dict) else None),
                "credit_pre_reserved": (ctx.get("credit_pre_reserved") if isinstance(ctx, dict) else None),
            }
        )

    # Aggregate counts by (stage, exc_type) to make triage trivial.
    counters: dict[str, int] = {}
    for it in items:
        key = f"{it.get('stage') or '?'}::{it.get('exc_type') or '?'}"
        counters[key] = counters.get(key, 0) + 1
    breakdown = [
        {"stage_exc": k, "count": v}
        for k, v in sorted(counters.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "window_hours": hours,
        "total": len(items),
        "breakdown": breakdown,
        "items": items,
    }


def _minimal_jpeg_bytes() -> bytes:
    """16x16 solid-grey JPEG — smallest payload that a vision model accepts.

    Used by the vision probe to reproduce the exact shape of
    ``OpenRouterLLM.analyze_image`` without sending any user content. Kept
    as a function (not a module-level const) so Pillow import stays lazy.
    """
    import io as _io
    from PIL import Image as _Image

    buf = _io.BytesIO()
    _Image.new("RGB", (16, 16), color=(128, 128, 128)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


async def _vision_probe_once(
    client,
    *,
    model: str,
    image_b64: str,
    use_response_format: bool,
    headers: dict[str, str],
    base_url: str,
) -> dict[str, Any]:
    """Fire one ``chat.completions`` call shaped like ``analyze_image``.

    Returns status / body snippet / latency. Never raises — any transport
    failure is reported as ``error``.
    """
    import time as _time
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": 'Return strictly {"ok":true} as JSON.'},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        }],
        "max_tokens": 100,
        "temperature": 0.0,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}

    t0 = _time.monotonic()
    try:
        r = await client.post(
            f"{base_url}/chat/completions", headers=headers, json=payload,
        )
        took_ms = int((_time.monotonic() - t0) * 1000)
        body = (r.text or "").strip().replace("\n", " ")
        return {
            "status": r.status_code,
            "body": body[:500],
            "took_ms": took_ms,
            "response_format": use_response_format,
        }
    except Exception as exc:
        took_ms = int((_time.monotonic() - t0) * 1000)
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "took_ms": took_ms,
            "response_format": use_response_format,
        }


@router.get("/diagnostics/provider-probe")
async def provider_probe(_key: str = Depends(_verify_internal_key)):
    """Actively probe the LLM provider using the live production API key.

    Goal: confirm in <5s whether OpenRouter would return 4xx/5xx *right now*
    with our credentials — without having to wait for a real user to hit
    "generate" and fail. Calls three cheap endpoints:

      * ``GET  /auth/key``          — key validity / credit (always free);
      * ``GET  /models``            — API reachable and model in catalog;
      * ``POST /chat/completions``  — vision call identical in shape to
        ``OpenRouterLLM.analyze_image`` (16×16 JPEG, same structured
        content blocks). Run twice: with ``response_format=json_object``
        and without, so a 400 exclusively caused by that parameter is
        immediately distinguishable from a safety / payload failure.

    Returns raw status codes + short body snippets. No PII involved.
    """
    import httpx as _httpx

    result: dict[str, Any] = {
        "base_url": settings.openrouter_base_url,
        "model": settings.openrouter_model,
        "key_present": bool(settings.openrouter_api_key.strip()),
    }
    if not result["key_present"]:
        result["error"] = "OPENROUTER_API_KEY is empty in settings"
        return result

    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    async with _httpx.AsyncClient(timeout=15.0) as client:
        # 1) key validity
        try:
            r = await client.get(
                f"{settings.openrouter_base_url}/auth/key", headers=headers
            )
            snippet = (r.text or "").strip().replace("\n", " ")
            result["auth_key"] = {
                "status": r.status_code,
                "body": snippet[:300],
            }
        except Exception as exc:
            result["auth_key"] = {"error": f"{type(exc).__name__}: {exc}"}

        # 2) model availability
        try:
            r = await client.get(
                f"{settings.openrouter_base_url}/models", headers=headers
            )
            result["models"] = {"status": r.status_code}
            if r.status_code == 200:
                try:
                    data = r.json()
                    ids = [m.get("id", "") for m in (data.get("data") or [])]
                    result["models"]["count"] = len(ids)
                    result["models"]["configured_model_in_catalog"] = (
                        settings.openrouter_model in ids
                    )
                except Exception:
                    result["models"]["parse_error"] = True
            else:
                body = (r.text or "").strip().replace("\n", " ")
                result["models"]["body"] = body[:300]
        except Exception as exc:
            result["models"] = {"error": f"{type(exc).__name__}: {exc}"}

        # 3) vision chat.completions — the real smoking gun
        try:
            jpeg = _minimal_jpeg_bytes()
            b64 = base64.b64encode(jpeg).decode("ascii")
            result["vision_json_mode"] = await _vision_probe_once(
                client,
                model=settings.openrouter_model,
                image_b64=b64,
                use_response_format=True,
                headers=headers,
                base_url=settings.openrouter_base_url,
            )
            result["vision_plain"] = await _vision_probe_once(
                client,
                model=settings.openrouter_model,
                image_b64=b64,
                use_response_format=False,
                headers=headers,
                base_url=settings.openrouter_base_url,
            )
        except Exception as exc:
            result["vision_probe_error"] = f"{type(exc).__name__}: {exc}"

    return result


def _synthetic_test_jpeg(size: int = 512) -> bytes:
    """Build a deterministic ``size×size`` JPEG for synthetic pipeline probes.

    We intentionally draw a simple two-tone gradient with a crude face-like
    oval so face-presence heuristics downstream don't auto-reject, but the
    key point is this endpoint *bypasses* preprocess/face gates and calls
    the mode service directly — see ``synthetic_analyze``.
    """
    import io as _io
    from PIL import Image as _Image, ImageDraw as _ImageDraw

    img = _Image.new("RGB", (size, size), color=(210, 200, 190))
    draw = _ImageDraw.Draw(img)
    cx, cy, r = size // 2, size // 2, size // 4
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(230, 200, 180))
    draw.ellipse((cx - r // 2, cy - r // 3, cx - r // 4, cy - r // 5), fill=(50, 40, 30))
    draw.ellipse((cx + r // 4, cy - r // 3, cx + r // 2, cy - r // 5), fill=(50, 40, 30))
    buf = _io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@router.post("/diagnostics/synthetic-analyze")
async def synthetic_analyze(
    mode: str = Query("social", description="Analysis mode: rating|dating|cv|social|emoji"),
    _key: str = Depends(_verify_internal_key),
):
    """Reproduce ``OpenRouterLLM.analyze_image`` with the production prompt.

    Unlike a real task this endpoint:

    * skips DB / Redis / preprocess — goes straight to the mode service;
    * uses a deterministic synthetic JPEG (no user content);
    * never retries on 4xx (same tenacity policy as worker — we inherit it
      from ``OpenRouterLLM`` itself, not re-wrap);
    * unwraps ``RetryError`` / ``PipelineStageError`` and returns the true
      ``httpx.HTTPStatusError`` body + status code + URL.

    This is the single fastest path to get the real 4xx that kills
    generation in production, without waiting for a user to hit "generate".
    """
    import time as _time
    from src.models.enums import AnalysisMode as _AnalysisMode
    from src.orchestrator.router import ModeRouter as _ModeRouter
    from src.prompts.engine import PromptEngine as _PromptEngine
    from src.providers.factory import get_llm as _get_llm
    from src.services.ai_transfer_guard import task_context_scope as _task_context_scope
    from src.workers.tasks import (
        _format_task_error as _fmt_err,
        _unwrap_exception as _unwrap,
        _http_status_of as _http_status,
    )

    try:
        mode_enum = _AnalysisMode(mode.strip().lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode}'")

    llm = _get_llm()
    router = _ModeRouter(llm, _PromptEngine())
    service = router.get_service(mode_enum)
    image = _synthetic_test_jpeg(512)

    # Diagnostics run outside the normal AnalysisPipeline, so we have to
    # open an explicit task_context_scope — otherwise the AI-transfer guard
    # trips on ``no_pipeline_context`` before the LLM call even goes out.
    guard_ctx = {"policy_flags": build_policy_flags({
        "consent_data_processing": True,
        "consent_ai_transfer": True,
    })}

    t0 = _time.monotonic()
    try:
        with _task_context_scope(guard_ctx):
            if mode_enum == _AnalysisMode.CV:
                res = await service.analyze(image, profession="синтетический тест")
            else:
                res = await service.analyze(image)
        took_ms = int((_time.monotonic() - t0) * 1000)
        public = res.model_dump() if hasattr(res, "model_dump") else (
            res.dict() if hasattr(res, "dict") else {"repr": repr(res)[:300]}
        )
        return {
            "ok": True,
            "mode": mode_enum.value,
            "model": settings.openrouter_model,
            "took_ms": took_ms,
            "keys": sorted(public.keys()) if isinstance(public, dict) else None,
        }
    except Exception as exc:
        took_ms = int((_time.monotonic() - t0) * 1000)
        original = _unwrap(exc)
        response = getattr(original, "response", None)
        body = ""
        if response is not None:
            try:
                body = (getattr(response, "text", "") or "").strip().replace("\n", " ")
            except Exception:
                body = ""
        request = getattr(original, "request", None)
        url = getattr(request, "url", None) if request is not None else None
        return {
            "ok": False,
            "mode": mode_enum.value,
            "model": settings.openrouter_model,
            "took_ms": took_ms,
            "exc_type": type(original).__name__,
            "exc_class_chain": type(exc).__name__,
            "http_status": _http_status(original),
            "body": body[:800],
            "url": str(url) if url is not None else None,
            "repr": repr(original)[:400],
            "error_message": _fmt_err(exc),
        }
    # NB: do NOT close ``llm`` here — ``get_llm()`` is a module-level
    # ``lru_cache`` singleton shared with the rest of the FastAPI process.
    # Closing it would poison every subsequent request with
    # ``RuntimeError: Cannot send a request, as the client has been closed``.
