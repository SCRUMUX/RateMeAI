from __future__ import annotations

import logging

from src.config import settings
from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode

logger = logging.getLogger(__name__)


class EmojiService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes) -> dict:
        from src.utils.consensus import consensus_analyze

        prompt = self._prompt_engine.build(AnalysisMode.EMOJI)
        raw = await consensus_analyze(
            self._llm, image_bytes, prompt,
            temperature=settings.scoring_temperature,
            n=settings.scoring_consensus_samples,
        )
        return raw
