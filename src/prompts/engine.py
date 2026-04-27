from __future__ import annotations

from src.models.enums import AnalysisMode
from src.prompts import rating, dating, cv, social, emoji
from src.prompts import image_gen as ig
from src.prompts import perception as _perception  # noqa: F401 — ensures perception module loads


# Direct-dispatch table for the framing/target_model/gender-aware
# builders. Emoji is intentionally absent — its builder has a different
# signature and does not consume target_model/framing.
_DIRECT_IMAGE_BUILDERS = {
    AnalysisMode.DATING: ig.build_dating_prompt,
    AnalysisMode.CV: ig.build_cv_prompt,
    AnalysisMode.SOCIAL: ig.build_social_prompt,
}


_PROMPT_MAP = {
    AnalysisMode.RATING: rating.build_prompt,
    AnalysisMode.DATING: dating.build_prompt,
    AnalysisMode.CV: cv.build_prompt,
    AnalysisMode.SOCIAL: social.build_prompt,
    AnalysisMode.EMOJI: emoji.build_prompt,
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
        framing: str | None = None,
    ) -> str:
        mode_str = _MODE_VALUE_MAP.get(mode, mode.value)
        variant = (
            ig.resolve_style_variant(mode_str, style, variant_id)
            if variant_id
            else None
        )

        if mode in _DIRECT_IMAGE_BUILDERS:
            return _DIRECT_IMAGE_BUILDERS[mode](
                style=style,
                base_description=base_description,
                gender=gender,
                input_hints=input_hints,
                variant=variant,
                target_model=target_model,
                framing=framing,
            )

        if mode == AnalysisMode.EMOJI:
            return ig.build_emoji_prompt(base_description, gender=gender)

        raise ValueError(f"No image prompt for mode: {mode}")

    def build_image_prompt_v2(
        self,
        mode: AnalysisMode,
        style: str = "",
        base_description: str = "",
        gender: str = "male",
        input_hints: dict | None = None,
        variant_id: str = "",
        target_model: str = "gpt_image_2",
        framing: str | None = None,
        out_substitutions: list[dict[str, str]] | None = None,
    ) -> str | None:
        """v2 prompt path — :class:`StyleSpecV2` + composition + wrapper.

        Additive companion to :meth:`build_image_prompt`. Returns
        ``None`` when the requested style is not registered as a v2
        spec so the executor can transparently fall back to the v1
        path. When the spec IS v2 (and the caller has already
        checked the ``unified_prompt_v2_enabled`` flag) the returned
        string is the final prompt for ``target_model``.

        ``out_substitutions``: optional output list. When supplied, the
        IR's :attr:`CompositionIR.substitutions` are extended into it
        so the executor can surface a post-generation hint to the user
        without needing to expose the IR. Untouched on the v1 fallback
        path (caller-provided list stays empty).

        Emoji intentionally stays on the legacy path; its builder has
        a different signature and does not benefit from the slot-based
        composition.
        """
        if mode not in _DIRECT_IMAGE_BUILDERS:
            return None

        mode_str = _MODE_VALUE_MAP.get(mode, mode.value)

        from src.prompts.image_gen import STYLE_REGISTRY as _REG
        from src.prompts.style_schema_v2 import StyleSpecV2

        spec = _REG.get_v2(mode_str, style)
        if not isinstance(spec, StyleSpecV2):
            return None

        from src.prompts.composition_builder import build_composition
        from src.prompts.image_gen import (
            _DOCUMENT_STYLE_KEYS,
            _dating_social_change_instruction,
        )
        from src.prompts.model_wrappers import wrap_for_model

        is_doc = mode_str == "cv" and style in _DOCUMENT_STYLE_KEYS

        if is_doc:
            change_instruction = (
                "Replace background with a clean neutral backdrop and clothing "
                "with a simple solid-color top, bare head. Head centered, "
                "shoulders straight, eyes open looking at camera, mouth closed."
            )
        elif mode_str in ("dating", "social"):
            change_instruction = _dating_social_change_instruction(mode_str, style)
        else:  # non-doc CV
            change_instruction = (
                "Change the background and clothing to professional attire "
                "for the person in the reference photo."
            )

        ir = build_composition(
            spec,
            mode=mode_str,
            change_instruction=change_instruction,
            input_hints=input_hints,
            framing=framing,
            gender=gender,
            strict=(not variant_id),
            is_document=is_doc,
        )
        if out_substitutions is not None and ir.substitutions:
            out_substitutions.extend(ir.substitutions)
        return wrap_for_model(ir, target_model)

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
