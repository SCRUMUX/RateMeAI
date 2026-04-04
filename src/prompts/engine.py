from __future__ import annotations

from src.models.enums import AnalysisMode
from src.prompts import rating, dating, cv, emoji
from src.prompts import image_gen as ig

_PROMPT_MAP = {
    AnalysisMode.RATING: rating.build_prompt,
    AnalysisMode.DATING: dating.build_prompt,
    AnalysisMode.CV: cv.build_prompt,
    AnalysisMode.EMOJI: emoji.build_prompt,
}

_IMAGE_PROMPT_MAP = {
    AnalysisMode.DATING: lambda style, _desc: ig.build_dating_prompt(style),
    AnalysisMode.CV: lambda style, _desc: ig.build_cv_prompt(style),
    AnalysisMode.EMOJI: lambda _style, desc: ig.build_emoji_prompt(desc),
}


class PromptEngine:
    def build(self, mode: AnalysisMode, context: dict | None = None) -> str:
        builder = _PROMPT_MAP.get(mode)
        if builder is None:
            raise ValueError(f"Unknown mode: {mode}")
        return builder(context or {})

    def build_image_prompt(self, mode: AnalysisMode, style: str = "", base_description: str = "") -> str:
        builder = _IMAGE_PROMPT_MAP.get(mode)
        if builder is None:
            raise ValueError(f"No image prompt for mode: {mode}")
        return builder(style, base_description)
