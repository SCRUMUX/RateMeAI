from __future__ import annotations

import logging

from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine
from src.models.enums import AnalysisMode

logger = logging.getLogger(__name__)


class EmojiService:
    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._llm = llm
        self._prompt_engine = prompt_engine

    async def analyze(self, image_bytes: bytes) -> dict:
        prompt = self._prompt_engine.build(AnalysisMode.EMOJI)
        raw = await self._llm.analyze_image(image_bytes, prompt)
        return raw
