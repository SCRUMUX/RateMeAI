from __future__ import annotations

import logging

from src.models.enums import AnalysisMode
from src.prompts import rating, dating, cv, social, emoji
from src.prompts import image_gen as ig
from src.prompts import perception as _perception  # noqa: F401 — ensures perception module loads

logger = logging.getLogger(__name__)


class StyleNotFoundError(LookupError):
    """Raised when ``build_image_prompt`` cannot resolve a photo style.

    v4.1 (May 2026): the photo prompt path has no v1 fallback. If the
    style is not registered as v3 (or v3-promoted from v2), the caller
    must surface the error rather than silently produce a degraded
    legacy-formatted prompt.
    """


def _scenario_image_overrides(scenario_slug: str | None) -> str:
    """Resolve scenario-level prompt overrides (Phase 2 Scenario Engine).

    Returns the ``image_instructions`` string from
    ``data/scenarios.json`` for the given slug, or an empty string when
    no scenario / no overrides apply. Failures (registry not loaded,
    bad JSON) degrade silently — the prompt is built without the
    overrides instead of erroring the request.
    """

    if not scenario_slug:
        return ""
    try:
        from src.scenarios import get_scenario as _get_scenario

        scenario = _get_scenario(scenario_slug)
    except Exception:  # pragma: no cover — defensive
        logger.exception("scenario_registry_load_failed slug=%s", scenario_slug)
        return ""
    if scenario is None or not scenario.enabled:
        return ""
    overrides = scenario.prompt_overrides
    if overrides is None:
        return ""
    return (overrides.image_instructions or "").strip()


# v4.1: photo modes for which build_image_prompt routes through the
# slot-based v3 path. Emoji stays on its own text-to-image builder
# (different signature, no edit reference).
_PHOTO_MODES = (AnalysisMode.DATING, AnalysisMode.CV, AnalysisMode.SOCIAL)


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
    def build(
        self,
        mode: AnalysisMode,
        context: dict | None = None,
        lang: str | None = None,
    ) -> str:
        """Build the analysis system prompt.

        ``lang`` selects the RU/EN templates for the analysis builders
        that opted into language awareness in 1.59.0
        (``dating``/``cv``/``social``). When omitted, the resolver in
        ``perception._resolve_lang`` falls back to
        ``settings.resolved_market_id`` so existing call sites keep
        working unchanged. Builders that have no ``lang`` parameter
        (rating, emoji) silently ignore the argument — kwargs only
        flow into builders that explicitly accept them.
        """
        builder = _PROMPT_MAP.get(mode)
        if builder is None:
            raise ValueError(f"Unknown mode: {mode}")
        if lang is not None:
            try:
                return builder(context or {}, lang=lang)  # type: ignore[call-arg]
            except TypeError:
                pass
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
        scenario_slug: str | None = None,
    ) -> str:
        """v4.1 single-path entrypoint for image prompt building.

        Photo modes (dating / cv / social) route through
        :meth:`build_image_prompt_v2` which always finds a registered
        v3 spec — either native or auto-promoted from v2. Emoji stays
        on its dedicated text-to-image builder.

        Raises :class:`StyleNotFoundError` for an unregistered photo
        style — there is no v1 fallback in v4.1.
        """
        if mode == AnalysisMode.EMOJI:
            base_prompt = ig.build_emoji_prompt(base_description, gender=gender)
        elif mode in _PHOTO_MODES:
            base_prompt = self.build_image_prompt_v2(
                mode,
                style=style,
                base_description=base_description,
                gender=gender,
                input_hints=input_hints,
                variant_id=variant_id,
                target_model=target_model,
                framing=framing,
                scenario_slug=scenario_slug,
            )
            if base_prompt is None:
                raise StyleNotFoundError(
                    f"Style {style!r} not registered for mode {mode.value!r}. "
                    "Every photo style must have a v3 spec (native or "
                    "v2-promoted)."
                )
            return base_prompt  # scenario already merged inside v2
        else:
            raise ValueError(f"No image prompt for mode: {mode}")

        scenario_extra = _scenario_image_overrides(scenario_slug)
        if scenario_extra:
            return f"{base_prompt}\n\n{scenario_extra}"
        return base_prompt

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
        seed: int | None = None,
        out_resolved_slots: dict[str, object] | None = None,
        scenario_slug: str | None = None,
    ) -> str | None:
        """Slot-based prompt path — prefers :class:`StyleSpecV3` and
        falls back to :class:`StyleSpecV2`.

        Returns ``None`` when neither schema has the requested style,
        so the executor can transparently fall back to the v1 path.

        Args:
            seed: optional integer seed for deterministic sampling on
                the v3 path. Ignored on the v2 path (which has no
                first-class random pools — its diversity comes from
                the soft-substitution flow only).
            out_resolved_slots: optional output dict. When supplied,
                the v3 path writes the :class:`ResolvedSlots` payload
                into it so the executor can persist the rolled values
                + return them to the frontend (badge rendering +
                anti-repeat for "Другой вариант"). Untouched on the
                v2 path.
            out_substitutions: optional output list. When supplied,
                soft-substitution records from the IR are appended so
                the executor can surface a post-generation hint to
                the user.

        Emoji intentionally stays on the legacy path; its builder has
        a different signature and does not benefit from the slot-based
        composition.
        """
        if mode not in _PHOTO_MODES:
            return None

        mode_str = _MODE_VALUE_MAP.get(mode, mode.value)

        from src.prompts.image_gen import STYLE_REGISTRY as _REG
        from src.prompts.style_schema_v2 import StyleSpecV2
        from src.prompts.style_schema_v3 import StyleSpecV3

        # v4.1: single-path resolution. Always prefer the v3 spec —
        # the v3 loader auto-promotes v2 specs without a native v3
        # sibling, so any registered photo style returns a v3 here.
        # The v2 lookup remains as a defensive fallback for
        # mid-bootstrap states where the v3 loader has not yet run.
        spec_v3 = _REG.get_v3(mode_str, style)
        spec = spec_v3 if spec_v3 is not None else _REG.get_v2(mode_str, style)

        if not isinstance(spec, (StyleSpecV2, StyleSpecV3)):
            return None

        from src.prompts.composition_builder import (
            build_composition,
            build_composition_v3,
        )
        from src.prompts.image_gen import (
            _DOCUMENT_STYLE_KEYS,
            _dating_social_change_instruction,
        )
        from src.prompts.model_wrappers import wrap_for_model

        is_doc = mode_str == "cv" and style in _DOCUMENT_STYLE_KEYS

        if is_doc:
            # Documents keep the strict ID-photo wording — vendor
            # policy demands a clean backdrop, solid-color top and
            # locked head/shoulders pose.
            change_instruction = (
                "Replace background with a clean neutral backdrop and clothing "
                "with a simple solid-color top, bare head. Head centered, "
                "shoulders straight, eyes open looking at camera, mouth closed."
            )
        else:
            # v4.1: every non-doc photo style — dating, social AND
            # non-doc CV — shares the Google-formula opener. The
            # per-style scene/wardrobe slots drive the actual scene
            # change.
            change_instruction = _dating_social_change_instruction(mode_str, style)

        if isinstance(spec, StyleSpecV3):
            ir = build_composition_v3(
                spec,
                mode=mode_str,
                change_instruction=change_instruction,
                input_hints=input_hints,
                framing=framing,
                gender=gender,
                strict=(not variant_id),
                is_document=is_doc,
                seed=seed,
            )
            if out_resolved_slots is not None:
                # 1.32.0 — forward the full ``ResolvedSlots`` payload
                # from the sampler. The IR flattens trigger/time/season
                # into ``scene``, so without this branch the UI loses
                # those fields. We fall back to the previous IR-derived
                # dict only if the IR somehow ends up without
                # ``resolved_slots`` attached (defensive — should not
                # happen for v3).
                from src.prompts.style_schema_v3 import ResolvedSlots

                if isinstance(ir.resolved_slots, ResolvedSlots):
                    out_resolved_slots.update(ir.resolved_slots.to_dict())
                    out_resolved_slots["expression"] = ir.expression
                else:
                    out_resolved_slots.update(
                        {
                            "scene": ir.scene,
                            "lighting": ir.lighting,
                            "weather": ir.weather,
                            "clothing": ir.clothing,
                            "expression": ir.expression,
                            "substitutions": [dict(s) for s in ir.substitutions],
                        }
                    )
        else:
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
        wrapped = wrap_for_model(ir, target_model)
        scenario_extra = _scenario_image_overrides(scenario_slug)
        if scenario_extra:
            return f"{wrapped}\n\n{scenario_extra}"
        return wrapped

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
