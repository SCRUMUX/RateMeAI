from __future__ import annotations

from src.models.enums import AnalysisMode
from src.prompts import rating, dating, cv, social, emoji
from src.prompts import image_gen as ig
from src.prompts import perception as _perception  # noqa: F401 — ensures perception module loads

_PROMPT_MAP = {
    AnalysisMode.RATING: rating.build_prompt,
    AnalysisMode.DATING: dating.build_prompt,
    AnalysisMode.CV: cv.build_prompt,
    AnalysisMode.SOCIAL: social.build_prompt,
    AnalysisMode.EMOJI: emoji.build_prompt,
}

_IMAGE_PROMPT_MAP = {
    AnalysisMode.DATING: lambda style, _desc: ig.build_dating_prompt(style),
    AnalysisMode.CV: lambda style, _desc: ig.build_cv_prompt(style),
    AnalysisMode.SOCIAL: lambda style, _desc: ig.build_social_prompt(style),
    AnalysisMode.EMOJI: lambda _style, desc: ig.build_emoji_prompt(desc),
}

_MODE_STYLE_DICTS: dict[AnalysisMode, dict[str, str]] = {
    AnalysisMode.DATING: ig.DATING_STYLES,
    AnalysisMode.CV: ig.CV_STYLES,
    AnalysisMode.SOCIAL: ig.SOCIAL_STYLES,
}

_MODE_PERSONALITY_DICTS: dict[AnalysisMode, dict[str, str]] = {
    AnalysisMode.DATING: ig.DATING_PERSONALITIES,
    AnalysisMode.CV: ig.CV_PERSONALITIES,
    AnalysisMode.SOCIAL: ig.SOCIAL_PERSONALITIES,
}

_EXPRESSION_STEPS = {"expression_hint"}


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

    def build_step_prompt(self, step_template: str, style: str, mode: AnalysisMode, enhancement_level: int = 0) -> str:
        """Build a prompt for a single multi-pass pipeline step."""
        if step_template in _EXPRESSION_STEPS:
            mode_dict = _MODE_PERSONALITY_DICTS.get(mode)
        else:
            mode_dict = _MODE_STYLE_DICTS.get(mode)
        return ig.build_step_prompt(step_template, style, mode_dict, enhancement_level=enhancement_level)
