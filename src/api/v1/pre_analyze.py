from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from redis.asyncio import Redis

from src.config import settings
from src.models.db import User
from src.models.enums import AnalysisMode
from src.models.schemas import PreAnalysisResponse, RatingResult
from src.api.deps import get_redis, get_auth_user
from src.orchestrator.router import ModeRouter
from src.providers.factory import get_llm
from src.prompts.engine import PromptEngine
from src.utils.humanize import humanize_result_scores
from src.utils.image import validate_and_normalize, has_face_heuristic
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
    image: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.DATING),
    profession: str = Form(""),
    user: User = Depends(get_auth_user),
    redis: Redis = Depends(get_redis),
):
    if mode not in (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL):
        raise HTTPException(status_code=400, detail="Pre-analyze supports dating, cv, social modes only")

    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 10MB")

    try:
        image_bytes, _meta = validate_and_normalize(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not has_face_heuristic(image_bytes):
        raise HTTPException(status_code=400, detail="На фото не обнаружено лицо. Загрузи портретное фото.")

    if settings.is_edge:
        import base64 as _b64
        from src.services.remote_ai import get_remote_ai, RemoteAIError
        try:
            remote = get_remote_ai()
            result_data = await remote.pre_analyze(
                image_b64=_b64.b64encode(image_bytes).decode(),
                mode=mode.value,
                profession=profession.strip(),
            )
            return PreAnalysisResponse(**result_data)
        except RemoteAIError as exc:
            logger.error("Edge pre-analyze proxy failed: %s", exc)
            raise HTTPException(status_code=502, detail="Не удалось выполнить анализ через основной сервер") from exc

    mode_router = _get_router()
    service = mode_router.get_service(mode)

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
            preanalysis_cache_key(pre_id),
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
    )


def _extract_composite_score(mode: AnalysisMode, d: dict) -> float:
    if mode == AnalysisMode.DATING:
        return float(d.get("dating_score", 0))
    if mode == AnalysisMode.SOCIAL:
        return float(d.get("social_score", 0))
    if mode == AnalysisMode.CV:
        vals = [float(d.get(k, 0)) for k in ("trust", "competence", "hireability") if d.get(k) is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0
    return 0.0
