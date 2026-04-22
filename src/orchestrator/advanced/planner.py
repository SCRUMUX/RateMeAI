"""Reserved: multi-pass Pipeline Planner.

The planner generates a JSON-compatible execution plan per task based on
analysis mode, style and enhancement level. It is currently **not**
invoked by the main runtime (``settings.multi_pass_enabled=False`` and
``policy.single_provider_call=True``) but is preserved verbatim as the
foundation for:

* premium / HD retouch scenarios with multi-step gate retries;
* compliance-loop for document scenarios (passport/ID) where a single
  pass cannot satisfy anatomy + background constraints simultaneously;
* N-variant generation with budget enforcement.

See ``docs/architecture/reserved.md`` for how to activate this code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import settings
from src.models.enums import AnalysisMode
from src.orchestrator.advanced.enhancement_levels import level_for_depth


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


class PipelinePlanner:
    """Generate a PipelinePlan based on mode, style and enhancement level."""

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


__all__ = ["PipelinePlan", "PipelinePlanner", "PipelineStep"]
