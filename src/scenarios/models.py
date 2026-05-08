"""Scenario dataclasses.

Frozen dataclasses make scenarios safe to share across threads (the
worker / API process / bot all read the same registry) and trivially
hashable for caching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.models.enums import AnalysisMode

ScenarioKind = Literal["core", "document", "visa"]
ScenarioPipelineProfile = Literal["simple", "advanced"]
ScenarioStep3Mode = Literal["styles", "document_formats"]


@dataclass(frozen=True)
class OutputSpec:
    """Physical photo target: size, dpi, aspect, background.

    ``aspect_key`` is the lookup key into
    :data:`src.orchestrator.executor._CV_DOCUMENT_ASPECT` so postprocess
    can crop to the right ratio without scenario-specific code.
    """

    size_mm: tuple[float, float] | None = None
    dpi: int = 300
    background_color: str = "#FFFFFF"
    head_height_mm: tuple[float, float] | None = None
    aspect_key: str | None = None


@dataclass(frozen=True)
class VisaRequirements:
    """Read-only visa photo spec sourced from official guidelines.

    The fields are intentionally narrow enums so we never accidentally
    drift the prompt away from the official requirement (e.g. allowing
    glasses on a Schengen visa).
    """

    expression: Literal["neutral", "smile_allowed"] = "neutral"
    glasses: Literal["allowed", "forbidden", "no_tinted"] = "forbidden"
    head_covering: Literal[
        "forbidden",
        "forbidden_except_religious",
        "allowed",
    ] = "forbidden_except_religious"
    background: str = "uniform_white"
    shadows: Literal["allowed", "forbidden"] = "forbidden"
    compliance_source: str = ""


@dataclass(frozen=True)
class PromptOverrides:
    """Text injected into analysis / image-gen prompts.

    ``analysis_checklist`` is a list of natural-language bullets the
    pre-analysis LLM must verify before allowing the user to proceed.

    ``analysis_checklist_en`` is the English mirror surfaced on the
    EN/global build (``MARKET_ID != "ru"``). It is optional — when
    empty, :func:`src.services.visa_compliance.compliance_checklist`
    falls back to the Russian master copy so we never ship an empty
    panel even if a translation is still pending.

    ``image_instructions`` is a paragraph appended to the image-gen
    prompt right after the style block — typically the
    document-compliance hint ("uniform white background, neutral
    expression, no glasses, head height 32-36 mm").
    """

    analysis_checklist: tuple[str, ...] = ()
    analysis_checklist_en: tuple[str, ...] = ()
    image_instructions: str = ""


@dataclass(frozen=True)
class PaywallConfig:
    pack_qty: int = 1
    show_paywall: bool = True


@dataclass(frozen=True)
class AnalysisDisplay:
    """How the analysis result should be rendered on the SPA.

    For the regular flow we show ``perception_score / 10``. Visa and
    document-photo scenarios instead show an "approval probability"
    on a 0..100 scale, which is then bumped to a fixed
    ``success_probability_after_pct`` (e.g. 98.9) once the user
    successfully regenerates the photo. The mode itself is data-driven
    so the SPA can ship without per-scenario branching.
    """

    mode: Literal["score", "approval_probability"] = "score"
    success_probability_after_pct: float | None = None
    label_key: str | None = None


@dataclass(frozen=True)
class Scenario:
    slug: str
    kind: ScenarioKind
    api_mode: AnalysisMode
    pipeline_profile: ScenarioPipelineProfile = "simple"
    step3_mode: ScenarioStep3Mode = "styles"
    output_spec: OutputSpec | None = None
    requirements: VisaRequirements | None = None
    prompt_overrides: PromptOverrides | None = None
    paywall: PaywallConfig | None = None
    analysis_display: AnalysisDisplay | None = None
    landing_slug: str | None = None
    enabled: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """Shape used by ``GET /api/v1/scenarios`` (web SPA consumer).

        Sensitive prompt overrides are NOT exposed to the client. The
        SPA only needs routing/UX hints (slug, kind, step3_mode,
        paywall), so we keep the public contract minimal.
        """

        return {
            "slug": self.slug,
            "kind": self.kind,
            "api_mode": self.api_mode.value,
            "pipeline_profile": self.pipeline_profile,
            "step3_mode": self.step3_mode,
            "landing_slug": self.landing_slug,
            "enabled": self.enabled,
            "paywall": (
                {
                    "pack_qty": self.paywall.pack_qty,
                    "show_paywall": self.paywall.show_paywall,
                }
                if self.paywall
                else None
            ),
            "output_spec": (
                {
                    "size_mm": list(self.output_spec.size_mm)
                    if self.output_spec.size_mm
                    else None,
                    "dpi": self.output_spec.dpi,
                    "background_color": self.output_spec.background_color,
                    "head_height_mm": list(self.output_spec.head_height_mm)
                    if self.output_spec.head_height_mm
                    else None,
                    "aspect_key": self.output_spec.aspect_key,
                }
                if self.output_spec
                else None
            ),
            "analysis_display": (
                {
                    "mode": self.analysis_display.mode,
                    "success_probability_after_pct": self.analysis_display.success_probability_after_pct,
                    "label_key": self.analysis_display.label_key,
                }
                if self.analysis_display
                else None
            ),
        }
