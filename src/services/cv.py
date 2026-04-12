from __future__ import annotations

from src.config import settings
from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode
from src.models.schemas import CVResult
from src.services.perception_utils import extract_perception_scores, extract_perception_insights


class CVService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes, profession: str = "не указана") -> CVResult:
        from src.utils.consensus import consensus_analyze

        prompt = self._prompt_engine.build(AnalysisMode.CV, {"profession": profession})
        raw = await consensus_analyze(
            self._llm, image_bytes, prompt,
            temperature=settings.scoring_temperature,
            n=settings.scoring_consensus_samples,
        )

        return CVResult(
            profession=raw.get("profession", profession),
            trust=float(raw.get("trust", 5)),
            competence=float(raw.get("competence", 5)),
            hireability=float(raw.get("hireability", 5)),
            analysis=raw.get("analysis", ""),
            perception_scores=extract_perception_scores(raw),
            perception_insights=extract_perception_insights(raw),
        )
