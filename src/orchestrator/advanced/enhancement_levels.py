"""Reserved: enhancement levels used by the multi-pass planner.

The ``EnhancementLevel`` dataclass, the ``LEVELS`` table, and the
``level_for_depth`` helper drive step selection inside
:class:`~src.orchestrator.advanced.planner.PipelinePlanner`, which is
itself reserved for advanced / premium scenarios (see
``docs/architecture/reserved.md``). They are intentionally separated
from the engagement statistics (``SCENARIO_STYLES``, ``build_full_matrix``,
``matrix_stats``, ``EngagementSnapshot``) that continue to serve the
runtime bot + ``/api/v1/engagement/*`` endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnhancementLevel:
    level: int
    name: str
    steps: list[str]
    strength: float
    description: str


LEVELS: list[EnhancementLevel] = [
    EnhancementLevel(
        level=1,
        name="light",
        steps=["lighting_adjust", "skin_correction"],
        strength=0.30,
        description="\u0421\u0432\u0435\u0442 \u0438 \u0442\u043e\u043d \u043a\u043e\u0436\u0438",
    ),
    EnhancementLevel(
        level=2,
        name="medium",
        steps=["lighting_adjust", "skin_correction", "background_edit", "clothing_edit"],
        strength=0.50,
        description="+ \u0444\u043e\u043d \u0438 \u043e\u0434\u0435\u0436\u0434\u0430",
    ),
    EnhancementLevel(
        level=3,
        name="deep",
        steps=["lighting_adjust", "skin_correction", "background_edit", "clothing_edit", "expression_hint"],
        strength=0.60,
        description="+ \u0432\u044b\u0440\u0430\u0436\u0435\u043d\u0438\u0435",
    ),
    EnhancementLevel(
        level=4,
        name="complete",
        steps=["lighting_adjust", "skin_correction", "background_edit", "clothing_edit", "expression_hint", "style_overall"],
        strength=0.70,
        description="\u041f\u043e\u043b\u043d\u044b\u0439 \u0441\u0442\u0438\u043b\u044c",
    ),
]


def level_for_depth(depth: int) -> EnhancementLevel:
    idx = min(depth, len(LEVELS)) - 1
    return LEVELS[max(0, idx)]


__all__ = ["EnhancementLevel", "LEVELS", "level_for_depth"]
