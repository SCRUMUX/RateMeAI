from __future__ import annotations

import logging

from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode
from src.models.schemas import CVResult

logger = logging.getLogger(__name__)


class CVService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes, profession: str = "не указана") -> CVResult:
        prompt = self._prompt_engine.build(AnalysisMode.CV, {"profession": profession})
        raw = await self._llm.analyze_image(image_bytes, prompt)

        return CVResult(
            profession=raw.get("profession", profession),
            trust=float(raw.get("trust", 5)),
            competence=float(raw.get("competence", 5)),
            hireability=float(raw.get("hireability", 5)),
            analysis=raw.get("analysis", ""),
        )
