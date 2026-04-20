"""Pipeline Planner: generates a JSON-compatible execution plan per task.

The planner selects steps based on analysis mode and style, assigning
per-step quality gate thresholds and model preferences.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import settings
from src.models.enums import AnalysisMode
from src.orchestrator.enhancement_matrix import level_for_depth


@dataclass
class PipelineStep:
    step: str
    region: str
    prompt_template: str
    gate: dict[str, float] = field(default_factory=dict)
    model_preference: str = "remix"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "region": self.region,
            "prompt_template": self.prompt_template,
            "gate": self.gate,
            "model_preference": self.model_preference,
        }


@dataclass
class PipelinePlan:
    task_id: str
    intent: str
    steps: list[PipelineStep]
    global_gates: dict[str, float] = field(default_factory=dict)
    retry_policy: dict[str, Any] = field(default_factory=lambda: {"max_retries": 0, "on_fail": "accept"})
    cost_budget: float = 0.15

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "global_gates": self.global_gates,
            "retry_policy": self.retry_policy,
            "cost_budget": self.cost_budget,
        }


# Identity match gate: 0-10 scale (VLM-based), no embeddings. Thresholds are
# chosen to be strict enough to catch obvious person-swaps while tolerating
# cosmetic retouching / expression hints. See docs/PRIVACY_AUDIT.md §9 and
# src/services/quality_gates.py::QUALITY_CHECK_PROMPT for scoring semantics.
_DEFAULT_GLOBAL_GATES = {
    "identity_match": 8.0,
    "aesthetic_score": 6.0,
    "artifact_ratio": 0.05,
    "photorealism": 0.5,
    "naturalness": 1.0,
    "anatomy": 1.0,
    "niqe": 5.0,
}

_DATING_STEPS = [
    PipelineStep(
        step="background_edit",
        region="background",
        prompt_template="background_edit",
        gate={"identity_match": 7.5},
        model_preference="edit",
    ),
    PipelineStep(
        step="lighting_adjust",
        region="full",
        prompt_template="lighting_adjust",
        gate={"identity_match": 7.0},
        model_preference="edit",
    ),
    PipelineStep(
        step="expression_hint",
        region="face",
        prompt_template="expression_hint",
        gate={"identity_match": 6.5, "aesthetic_score": 6.0},
        model_preference="edit",
    ),
    PipelineStep(
        step="skin_correction",
        region="face",
        prompt_template="skin_correction",
        gate={"identity_match": 7.5},
        model_preference="edit",
    ),
]

_CV_STEPS = [
    PipelineStep(
        step="background_edit",
        region="background",
        prompt_template="background_edit",
        gate={"identity_match": 7.5},
        model_preference="edit",
    ),
    PipelineStep(
        step="clothing_edit",
        region="clothing",
        prompt_template="clothing_edit",
        gate={"identity_match": 7.5},
        model_preference="edit",
    ),
    PipelineStep(
        step="expression_hint",
        region="face",
        prompt_template="expression_hint",
        gate={"identity_match": 6.5},
        model_preference="edit",
    ),
]

_SOCIAL_STEPS = [
    PipelineStep(
        step="background_edit",
        region="background",
        prompt_template="background_edit",
        gate={"identity_match": 7.5},
        model_preference="edit",
    ),
    PipelineStep(
        step="style_overall",
        region="full",
        prompt_template="style_overall",
        gate={"identity_match": 7.0, "aesthetic_score": 6.0},
        model_preference="edit",
    ),
    PipelineStep(
        step="expression_hint",
        region="face",
        prompt_template="expression_hint",
        gate={"identity_match": 6.5},
        model_preference="edit",
    ),
]


_STEP_STRENGTH_KEYWORDS: dict[str, list[str]] = {
    "background_edit": ["фон", "background", "обстановка", "место"],
    "lighting_adjust": ["свет", "освещение", "lighting", "яркость"],
    "clothing_edit": ["одежда", "стиль одежды", "clothing", "outfit", "дресс"],
    "skin_correction": ["кожа", "skin", "цвет лица", "текстура"],
    "expression_hint": ["выражение", "улыбка", "expression", "взгляд", "эмоция"],
    "style_overall": [],
}

# TODO: Move to shared constants when UI needs human-readable step labels.
# STEP_PARAMETER_MAP: dict[str, list[str]] = {
#     "background_edit": ["presence", "appeal"],
#     "lighting_adjust": ["warmth", "appeal"],
#     "clothing_edit": ["presence"],
#     "expression_hint": ["warmth", "presence"],
#     "skin_correction": ["appeal"],
#     "style_overall": ["appeal", "presence"],
# }
#
# PARAMETER_LABELS: dict[str, str] = {
#     "warmth": "Теплота",
#     "presence": "Уверенность",
#     "appeal": "Привлекательность",
#     "authenticity": "Аутентичность",
# }
#
# STEP_LABELS: dict[str, str] = {
#     "background_edit": "фон и контекст",
#     "lighting_adjust": "освещение",
#     "clothing_edit": "стиль одежды",
#     "expression_hint": "выражение",
#     "skin_correction": "качество кожи",
#     "style_overall": "общий стиль",
# }


class PipelinePlanner:
    """Generate a PipelinePlan based on mode, style and analysis results."""

    def plan(
        self,
        mode: AnalysisMode,
        style: str,
        task_id: str,
        analysis_result: dict | None = None,
        enhancement_level: int = 0,
    ) -> PipelinePlan | None:
        """Return a multi-step plan, or None for modes that don't need one."""
        if mode in (AnalysisMode.RATING, AnalysisMode.EMOJI):
            return None

        steps_template = {
            AnalysisMode.DATING: _DATING_STEPS,
            AnalysisMode.CV: _CV_STEPS,
            AnalysisMode.SOCIAL: _SOCIAL_STEPS,
        }.get(mode)

        if not steps_template:
            return None

        steps = [
            PipelineStep(
                step=s.step,
                region=s.region,
                prompt_template=s.prompt_template,
                gate=dict(s.gate),
                model_preference=s.model_preference,
            )
            for s in steps_template
        ]

        if enhancement_level > 0:
            allowed = set(level_for_depth(enhancement_level).steps)
            steps = [s for s in steps if s.step in allowed]

        if analysis_result:
            steps = [s for s in steps if self._step_needed(s, analysis_result)]

        global_gates = dict(_DEFAULT_GLOBAL_GATES)
        global_gates["identity_match"] = settings.identity_match_threshold
        global_gates["aesthetic_score"] = settings.aesthetic_threshold
        global_gates["artifact_ratio"] = settings.artifact_threshold
        if settings.photorealism_enabled:
            global_gates["photorealism"] = settings.photorealism_threshold
        else:
            global_gates.pop("photorealism", None)

        return PipelinePlan(
            task_id=task_id,
            intent=f"{mode.value}:{style or 'default'}",
            steps=steps,
            global_gates=global_gates,
            cost_budget=settings.pipeline_budget_max_usd,
        )

    @staticmethod
    def _step_needed(step: PipelineStep, analysis_result: dict) -> bool:
        """Return False if the step's area is already a strength (no improvement needed)."""
        keywords = _STEP_STRENGTH_KEYWORDS.get(step.step, [])
        if not keywords:
            return True

        strengths_text = " ".join(
            str(s).lower() for s in analysis_result.get("strengths", [])
        )
        if not strengths_text:
            return True

        for kw in keywords:
            if kw.lower() in strengths_text:
                return False

        return True
