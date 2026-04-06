"""Enhancement Matrix — structured levels x styles x scenarios.

Defines what pipeline steps execute at each depth level, how
image generation strength progresses, and the full matrix of
style x level x scenario combinations for engagement depth.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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


SCENARIO_STYLES: dict[str, list[str]] = {
    "dating": ["warm_outdoor", "studio_elegant", "cafe"],
    "cv": ["corporate", "creative", "neutral"],
    "social": ["influencer", "luxury", "casual", "artistic"],
}


def styles_for_scenario(scenario: str) -> list[str]:
    return SCENARIO_STYLES.get(scenario, SCENARIO_STYLES["dating"])


@dataclass
class MatrixCell:
    scenario: str
    style: str
    level: int
    strength: float
    steps: list[str]


def build_full_matrix() -> list[MatrixCell]:
    """Enumerate all scenario x style x level combinations."""
    cells = []
    for scenario, styles in SCENARIO_STYLES.items():
        for style in styles:
            for lvl in LEVELS:
                cells.append(MatrixCell(
                    scenario=scenario,
                    style=style,
                    level=lvl.level,
                    strength=lvl.strength,
                    steps=list(lvl.steps),
                ))
    return cells


def matrix_stats() -> dict:
    """Summary statistics for monitoring/analytics."""
    total = 0
    by_scenario: dict[str, int] = {}
    for scenario, styles in SCENARIO_STYLES.items():
        count = len(styles) * len(LEVELS)
        by_scenario[scenario] = count
        total += count
    return {
        "total_combinations": total,
        "by_scenario": by_scenario,
        "levels": len(LEVELS),
    }


@dataclass
class EngagementSnapshot:
    user_id: int
    mode: str
    depth: int
    level: EnhancementLevel
    remaining_styles: list[str]
    total_matrix_cells: int

    @property
    def completion_pct(self) -> float:
        styles = SCENARIO_STYLES.get(self.mode, [])
        if not styles:
            return 0.0
        max_depth = len(styles) * len(LEVELS)
        return min(100.0, round(self.depth / max_depth * 100, 1))


def engagement_snapshot(user_id: int, mode: str, depth: int, current_style: str = "") -> EngagementSnapshot:
    """Build an engagement snapshot for analytics."""
    lvl = level_for_depth(depth)
    all_styles = styles_for_scenario(mode)
    remaining = [s for s in all_styles if s != current_style]
    stats = matrix_stats()
    return EngagementSnapshot(
        user_id=user_id,
        mode=mode,
        depth=depth,
        level=lvl,
        remaining_styles=remaining,
        total_matrix_cells=stats["total_combinations"],
    )
