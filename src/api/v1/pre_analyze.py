from __future__ import annotations

import hashlib
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
from src.utils.image import validate_and_normalize, has_face_heuristic
from src.utils.redis_keys import preanalysis_cache_key
from src.utils.security import extract_nsfw_from_analysis
from src.metrics import LLM_CALLS

logger = logging.getLogger(__name__)

router = APIRouter()

_SCORE_KEYS = ("dating_score", "trust", "competence", "hireability", "social_score")
_PERCEPTION_KEYS = ("warmth", "presence", "appeal")
_SCORE_FLOOR = 5.0
_PERCEPTION_FLOOR = 3.0
_PRE_ANALYSIS_TTL = 1800


def _humanize_score(raw: float, seed: str, floor: float = _SCORE_FLOOR) -> float:
    base = int(raw)
    raw_frac = raw - base
    h = int(hashlib.md5(seed.encode()).hexdigest()[:6], 16)
    frac = (h % 100) / 100.0
    if raw_frac > 0:
        frac = round(raw_frac + (frac - 0.5) * 0.1, 2)
    result = base + max(0.01, min(0.99, frac))
    result = max(floor, result)
    return round(min(9.99, result), 2)


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

    for sk in _SCORE_KEYS:
        if sk in result_dict and isinstance(result_dict[sk], (int, float)):
            result_dict[sk] = _humanize_score(float(result_dict[sk]), f"{pre_id}:{sk}")

    ps = result_dict.get("perception_scores")
    if isinstance(ps, dict):
        for pk in _PERCEPTION_KEYS:
            if pk in ps and isinstance(ps[pk], (int, float)):
                ps[pk] = _humanize_score(float(ps[pk]), f"{pre_id}:p:{pk}", floor=_PERCEPTION_FLOOR)
        result_dict["perception_scores"] = ps
    elif hasattr(ps, "model_dump"):
        ps_dict = ps.model_dump()
        for pk in _PERCEPTION_KEYS:
            if pk in ps_dict and isinstance(ps_dict[pk], (int, float)):
                ps_dict[pk] = _humanize_score(float(ps_dict[pk]), f"{pre_id}:p:{pk}", floor=_PERCEPTION_FLOOR)
        result_dict["perception_scores"] = ps_dict

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
