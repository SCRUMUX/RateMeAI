from __future__ import annotations

import logging

from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode
from src.models.schemas import DatingResult

logger = logging.getLogger(__name__)


class DatingService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes) -> DatingResult:
        prompt = self._prompt_engine.build(AnalysisMode.DATING)
        raw = await self._llm.analyze_image(image_bytes, prompt)

        return DatingResult(
            first_impression=raw.get("first_impression", ""),
            dating_score=float(raw.get("dating_score", 5)),
            strengths=raw.get("strengths", []),
            weaknesses=raw.get("weaknesses", []),
            variants=raw.get("variants", []),
        )
