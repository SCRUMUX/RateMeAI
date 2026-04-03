from __future__ import annotations

from src.models.enums import AnalysisMode
from src.prompts import rating, dating, cv, emoji

_PROMPT_MAP = {
    AnalysisMode.RATING: rating.build_prompt,
    AnalysisMode.DATING: dating.build_prompt,
    AnalysisMode.CV: cv.build_prompt,
    AnalysisMode.EMOJI: emoji.build_prompt,
}


class PromptEngine:
    def build(self, mode: AnalysisMode, context: dict | None = None) -> str:
        builder = _PROMPT_MAP.get(mode)
        if builder is None:
            raise ValueError(f"Unknown mode: {mode}")
        return builder(context or {})
