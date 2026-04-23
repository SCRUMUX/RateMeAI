from __future__ import annotations

import logging

from pydantic import ValidationError

from src.config import settings
from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult
from src.services.perception_utils import (
    extract_perception_scores,
    extract_perception_insights,
)

logger = logging.getLogger(__name__)


class RatingService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes) -> RatingResult:
        from src.utils.consensus import consensus_analyze

        prompt = self._prompt_engine.build(AnalysisMode.RATING)
        raw = await consensus_analyze(
            self._llm,
            image_bytes,
            prompt,
            temperature=settings.scoring_temperature,
            n=settings.scoring_consensus_samples,
        )

        try:
            result = RatingResult.model_validate(raw)
        except ValidationError:
            logger.warning("LLM returned invalid structure, attempting fix: %s", raw)
            result = self._try_fix(raw)

        if result.perception_scores is None:
            result.perception_scores = extract_perception_scores(raw)
        if not result.perception_insights:
            result.perception_insights = extract_perception_insights(raw)

        return result

    @staticmethod
    def _try_fix(raw: dict) -> RatingResult:
        """Best-effort normalization of LLM output."""
        perception = raw.get("perception", {})
        if not perception and "trust" in raw:
            perception = {
                "trust": raw.get("trust", 5),
                "attractiveness": raw.get("attractiveness", 5),
                "emotional_expression": raw.get(
                    "emotional_expression", raw.get("emotion", "нейтральное")
                ),
            }

        return RatingResult(
            score=float(raw.get("score", 5)),
            perception={
                "trust": float(perception.get("trust", 5)),
                "attractiveness": float(perception.get("attractiveness", 5)),
                "emotional_expression": str(
                    perception.get("emotional_expression", "нейтральное")
                ),
            },
            perception_scores=extract_perception_scores(raw),
            perception_insights=extract_perception_insights(raw),
            insights=raw.get("insights", ["Анализ не удалось полностью распарсить"]),
            recommendations=raw.get(
                "recommendations", ["Попробуй загрузить фото с лучшим освещением"]
            ),
        )
