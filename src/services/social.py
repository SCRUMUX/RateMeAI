from __future__ import annotations

from src.config import settings
from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode
from src.models.schemas import SocialResult
from src.services.perception_utils import (
    extract_perception_scores,
    extract_perception_insights,
)


class SocialService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes) -> SocialResult:
        from src.utils.consensus import consensus_analyze

        prompt = self._prompt_engine.build(AnalysisMode.SOCIAL)
        raw = await consensus_analyze(
            self._llm,
            image_bytes,
            prompt,
            temperature=settings.scoring_temperature,
            n=settings.scoring_consensus_samples,
        )

        return SocialResult(
            first_impression=raw.get("first_impression", ""),
            social_score=float(raw.get("social_score", 5)),
            strengths=raw.get("strengths", []),
            weaknesses=raw.get("weaknesses", raw.get("enhancement_opportunities", [])),
            enhancement_opportunities=raw.get(
                "enhancement_opportunities", raw.get("weaknesses", [])
            ),
            variants=raw.get("variants", []),
            perception_scores=extract_perception_scores(raw),
            perception_insights=extract_perception_insights(raw),
        )
