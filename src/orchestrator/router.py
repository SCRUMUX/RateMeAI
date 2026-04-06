from __future__ import annotations

from src.models.enums import AnalysisMode
from src.services.rating import RatingService
from src.services.dating import DatingService
from src.services.cv import CVService
from src.services.social import SocialService
from src.services.emoji import EmojiService
from src.providers.base import LLMProvider
from src.prompts.engine import PromptEngine


class ModeRouter:
    """Resolves analysis mode to the corresponding service."""

    def __init__(self, llm: LLMProvider, prompt_engine: PromptEngine):
        self._services = {
            AnalysisMode.RATING: RatingService(llm, prompt_engine),
            AnalysisMode.DATING: DatingService(llm, prompt_engine),
            AnalysisMode.CV: CVService(llm, prompt_engine),
            AnalysisMode.SOCIAL: SocialService(llm, prompt_engine),
            AnalysisMode.EMOJI: EmojiService(llm, prompt_engine),
        }

    def get_service(self, mode: AnalysisMode):
        service = self._services.get(mode)
        if service is None:
            raise ValueError(f"Unsupported mode: {mode}")
        return service
