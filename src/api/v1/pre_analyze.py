from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from redis.asyncio import Redis

from src.config import settings
from src.models.db import User
from src.models.enums import AnalysisMode
from src.models.schemas import (
    PreAnalysisResponse,
    RatingResult,
    InputQualityPublic,
    InputQualityIssuePublic,
)
from src.api.deps import get_redis, require_consents
from src.orchestrator.router import ModeRouter
from src.providers.factory import get_llm
from src.prompts.engine import PromptEngine
from src.services.ai_transfer_guard import task_context_scope
from src.services.consent import (
    CONSENT_AI_TRANSFER,
    CONSENT_DATA_PROCESSING,
)
from src.services.input_quality import analyze_input_quality
from src.services.privacy import PrivacyLayer
from src.services.task_contract import build_policy_flags
from src.utils.humanize import humanize_result_scores
from src.utils.redis_keys import preanalysis_cache_key
from src.utils.security import extract_nsfw_from_analysis
from src.metrics import LLM_CALLS

logger = logging.getLogger(__name__)

router = APIRouter()

_PRE_ANALYSIS_TTL = 1800


def _build_mode_router() -> ModeRouter:
    llm = get_llm()
    return ModeRouter(llm, PromptEngine())


_router_instance: ModeRouter | None = None


def _get_router() -> ModeRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = _build_mode_router()
    return _router_instance


@router.post("", response_model=PreAnalysisResponse)
async def pre_analyze(
    request: Request,
    image: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.DATING),
    profession: str = Form(""),
    user: User = Depends(require_consents),
    redis: Redis = Depends(get_redis),
):
    if mode not in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL):
        raise HTTPException(status_code=400, detail="Pre-analyze supports dating, cv, social modes only")

    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    raw_bytes = await image.read()
    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    try:
        sanitized = PrivacyLayer.sanitize_and_normalize(raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        raw_bytes = b""  # noqa: F841 — explicit drop reference for GC
    image_bytes = sanitized.bytes_

    # Bind consent flags to the outbound AI guard ContextVar for this request.
    consent_snapshot = getattr(user, "_consents_snapshot", None) or {}
    ctx_flags = {
        "policy_flags": build_policy_flags(
            consent_data_processing=CONSENT_DATA_PROCESSING in consent_snapshot,
            consent_ai_transfer=CONSENT_AI_TRANSFER in consent_snapshot,
        ),
    }

    quality_report = analyze_input_quality(image_bytes)
    if not quality_report.can_generate:
        primary = quality_report.blocking[0]
        raise HTTPException(
            status_code=400,
            detail={
                "message": primary.message,
                "suggestion": primary.suggestion,
                "code": primary.code,
                "blocking_issues": [i.to_dict() for i in quality_report.blocking],
            },
        )

    input_quality_public = InputQualityPublic(
        can_generate=quality_report.can_generate,
        soft_warnings=[
            InputQualityIssuePublic(**i.to_dict()) for i in quality_report.soft_warnings
        ],
        blocking_issues=[],
    )

    if settings.uses_remote_ai:
        import base64 as _b64
        from src.services.remote_ai import get_remote_ai, RemoteAIError
        try:
            remote = get_remote_ai()
            result_data = await remote.pre_analyze(
                image_b64=_b64.b64encode(image_bytes).decode(),
                mode=mode.value,
                profession=profession.strip(),
                market_id=settings.resolved_market_id,
                trace_id=request.headers.get("x-trace-id", ""),
                policy_flags=ctx_flags["policy_flags"],
            )
            # Attach locally-computed input quality — remote AI does not see it.
            resp = PreAnalysisResponse(**result_data)
            resp.input_quality = input_quality_public
            return resp
        except RemoteAIError as exc:
            logger.error("Edge pre-analyze proxy failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Не удалось выполнить анализ через основной сервер: {exc}") from exc

    mode_router = _get_router()
    service = mode_router.get_service(mode)

    with task_context_scope(ctx_flags):
        if mode == AnalysisMode.CV:
            prof = profession.strip() or "не указана"
            result = await service.analyze(image_bytes, profession=prof)
        else:
            result = await service.analyze(image_bytes)
    LLM_CALLS.labels(purpose=f"preanalyze_{mode.value}").inc()

    raw_dict = result if isinstance(result, dict) else (result.model_dump() if hasattr(result, "model_dump") else result)

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

    try:
        await redis.set(
            preanalysis_cache_key(pre_id, settings.resolved_market_id),
            json.dumps(result_dict, default=str),
            ex=_PRE_ANALYSIS_TTL,
        )
    except Exception:
        logger.exception("Failed to cache pre-analysis %s", pre_id)

    score = _extract_composite_score(mode, result_dict)
    perception = result_dict.get("perception_scores", {})
    if hasattr(perception, "model_dump"):
        perception = perception.model_dump()

    insights = result_dict.get("perception_insights", [])
    if insights and hasattr(insights[0], "model_dump"):
        insights = [i.model_dump() for i in insights]

    opportunities = result_dict.get("enhancement_opportunities", [])

    return PreAnalysisResponse(
        pre_analysis_id=pre_id,
        mode=mode,
        first_impression=result_dict.get("first_impression", result_dict.get("analysis", "")),
        score=score,
        perception_scores=perception,
        perception_insights=insights,
        enhancement_opportunities=opportunities,
        input_quality=input_quality_public,
    )


def _extract_composite_score(mode: AnalysisMode, d: dict) -> float:
    def _safe_float(val, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    if mode == AnalysisMode.DATING:
        return _safe_float(d.get("dating_score"))
    if mode == AnalysisMode.SOCIAL:
        return _safe_float(d.get("social_score"))
    if mode == AnalysisMode.CV:
        vals = [_safe_float(d.get(k)) for k in ("trust", "competence", "hireability") if d.get(k) is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0
    return 0.0
