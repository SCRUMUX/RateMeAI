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
    AnalysisMode.DATING: lambda style,
    _desc,
    gender,
    q,
    variant: ig.build_dating_prompt(style, gender, input_hints=q, variant=variant),
    AnalysisMode.CV: lambda style, _desc, gender, q, variant: ig.build_cv_prompt(
        style, gender, input_hints=q, variant=variant
    ),
    AnalysisMode.SOCIAL: lambda style,
    _desc,
    gender,
    q,
    variant: ig.build_social_prompt(style, gender, input_hints=q, variant=variant),
    AnalysisMode.EMOJI: lambda _style,
    desc,
    gender,
    _q,
    _variant: ig.build_emoji_prompt(desc, gender=gender),
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

_MODE_VALUE_MAP: dict[AnalysisMode, str] = {
    AnalysisMode.DATING: "dating",
    AnalysisMode.CV: "cv",
    AnalysisMode.SOCIAL: "social",
}


class PromptEngine:
    def build(self, mode: AnalysisMode, context: dict | None = None) -> str:
        builder = _PROMPT_MAP.get(mode)
        if builder is None:
            raise ValueError(f"Unknown mode: {mode}")
        return builder(context or {})

    def build_image_prompt(
        self,
        mode: AnalysisMode,
        style: str = "",
        base_description: str = "",
        gender: str = "male",
        input_hints: dict | None = None,
        variant_id: str = "",
        target_model: str = "gpt_image_2",
    ) -> str:
        builder = _IMAGE_PROMPT_MAP.get(mode)
        if builder is None:
            raise ValueError(f"No image prompt for mode: {mode}")
        mode_str = _MODE_VALUE_MAP.get(mode, mode.value)
        variant = (
            ig.resolve_style_variant(mode_str, style, variant_id)
            if variant_id
            else None
        )

        # If the builder is one of the mode-specific builders, pass target_model
        if builder in (
            ig.build_dating_prompt,
            ig.build_cv_prompt,
            ig.build_social_prompt,
        ):
            return builder(
                style, base_description, gender, input_hints, variant, target_model
            )

        return builder(style, base_description, gender, input_hints, variant)

    def build_step_prompt(
        self,
        step_template: str,
        style: str,
        mode: AnalysisMode,
        enhancement_level: int = 0,
        gender: str = "male",
    ) -> str:
        """Build a prompt for a single multi-pass pipeline step."""
        mode_str = _MODE_VALUE_MAP.get(mode, mode.value)
        return ig.build_step_prompt(
            step_template,
            style,
            mode_str,
            gender=gender,
            enhancement_level=enhancement_level,
        )
