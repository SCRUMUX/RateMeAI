"""Scenario Engine — data-driven configuration layer over the photo pipeline.

A *scenario* binds a public landing page + wizard flow to a fixed
combination of:

- analysis ``AnalysisMode`` (which `ModeRouter` service runs scoring),
- pipeline profile (``simple`` = current single-pass; ``advanced``
  was the reserved compliance loop, retired in v1.71),
- output spec (size in mm, dpi, background, target aspect),
- optional document/visa requirements,
- optional prompt overrides injected into the image-gen builder,
- paywall / pricing config.

Scenarios are declared in ``data/scenarios.json`` (per-server, just like
``data/landing_content.json``). The registry is intentionally
*read-only at runtime*: feature flags are encoded as the ``enabled``
field on each scenario, so a merged-but-unannounced visa scenario stays
dark in production until its JSON entry flips.

This package is the Phase 2 deliverable from
``docs/architecture/scenario_platform.md``.
"""

from src.scenarios.models import (
    AnalysisDisplay,
    OutputSpec,
    PaywallConfig,
    PromptOverrides,
    Scenario,
    ScenarioKind,
    ScenarioPipelineProfile,
    ScenarioStep3Mode,
    VisaRequirements,
)
from src.scenarios.registry import (
    get_scenario,
    list_enabled_scenarios,
    list_scenarios,
)

__all__ = [
    "AnalysisDisplay",
    "OutputSpec",
    "PaywallConfig",
    "PromptOverrides",
    "Scenario",
    "ScenarioKind",
    "ScenarioPipelineProfile",
    "ScenarioStep3Mode",
    "VisaRequirements",
    "get_scenario",
    "list_enabled_scenarios",
    "list_scenarios",
]
