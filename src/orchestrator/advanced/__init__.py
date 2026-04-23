"""Reserved multi-pass orchestration.

This subpackage contains machinery that is **not part of the current
runtime** but is kept as the foundation for future premium / advanced
scenarios (HD retouch, compliance-loop for documents, N-variant
generation, capability-based FLUX/Reve routing).

Current runtime always runs ``AnalysisPipeline`` -> ``ImageGenerationExecutor.single_pass``.
Nothing in this package is imported from the hot path; it is referenced
only by:

* unit tests that exercise the planner / router data structures;
* the forthcoming Scenario Engine (Phase 2) which will opt specific
  scenarios into multi-pass via ``Scenario.pipeline_profile``;
* the FLUX integration (Phase 3) which will plug into
  :mod:`~src.orchestrator.advanced.model_router`.

See ``docs/architecture/reserved.md`` for the full map and the roadmap.
"""

from src.orchestrator.advanced.enhancement_levels import (
    EnhancementLevel,
    LEVELS,
    level_for_depth,
)
from src.orchestrator.advanced.execute_plan import AdvancedPipelineExecutor
from src.orchestrator.advanced.planner import (
    PipelinePlan,
    PipelinePlanner,
    PipelineStep,
)

__all__ = [
    "AdvancedPipelineExecutor",
    "EnhancementLevel",
    "LEVELS",
    "level_for_depth",
    "PipelinePlan",
    "PipelinePlanner",
    "PipelineStep",
]
