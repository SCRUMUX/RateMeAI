from __future__ import annotations

import logging

from pydantic import ValidationError

from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult

logger = logging.getLogger(__name__)


class RatingService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes) -> RatingResult:
        prompt = self._prompt_engine.build(AnalysisMode.RATING)
        raw = await self._llm.analyze_image(image_bytes, prompt)

        try:
            result = RatingResult.model_validate(raw)
        except ValidationError:
            logger.warning("LLM returned invalid structure, attempting fix: %s", raw)
            result = self._try_fix(raw)

        return result

    @staticmethod
    def _try_fix(raw: dict) -> RatingResult:
        """Best-effort normalization of LLM output."""
        perception = raw.get("perception", {})
        if not perception and "trust" in raw:
            perception = {
                "trust": raw.get("trust", 5),
                "attractiveness": raw.get("attractiveness", 5),
                "emotional_expression": raw.get("emotional_expression", raw.get("emotion", "нейтральное")),
            }

        return RatingResult(
            score=float(raw.get("score", 5)),
            perception={
                "trust": float(perception.get("trust", 5)),
                "attractiveness": float(perception.get("attractiveness", 5)),
                "emotional_expression": str(perception.get("emotional_expression", "нейтральное")),
            },
            insights=raw.get("insights", ["Анализ не удалось полностью распарсить"]),
            recommendations=raw.get("recommendations", ["Попробуйте загрузить фото с лучшим освещением"]),
        )
