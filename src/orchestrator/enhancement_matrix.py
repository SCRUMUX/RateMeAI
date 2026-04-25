"""Engagement matrix — scenario x style x level statistics.

The per-level step tables (:class:`EnhancementLevel`, :data:`LEVELS`,
:func:`level_for_depth`) are exclusively consumed by the reserved
multi-pass planner and therefore live in
:mod:`src.orchestrator.advanced.enhancement_levels`. They are re-exported
from this module for backwards compatibility with existing callers (the
bot ``mode_select`` handler in particular).

The engagement layer below (``SCENARIO_STYLES``, ``build_full_matrix``,
``matrix_stats``, ``EngagementSnapshot``) stays in the runtime surface:
it feeds ``/api/v1/engagement/*`` and the bot's progress display.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.orchestrator.advanced.enhancement_levels import (
    EnhancementLevel,
    LEVELS,
    level_for_depth,
)


SCENARIO_STYLES: dict[str, list[str]] = {
    "dating": [
        "warm_outdoor",
        "studio_elegant",
        "near_car",
        "in_car",
        "motorcycle",
        "yacht",
        "rooftop_city",
        "gym_fitness",
        "running",
        "tennis",
        "swimming_pool",
        "hiking",
        "cafe",
        "coffee_date",
        "restaurant",
        "bar_lounge",
        "cooking",
        "dog_lover",
        "travel",
        "beach_sunset",
        "art_gallery",
        "street_urban",
        "concert",
        # landmarks
        "paris_eiffel",
        "nyc_brooklyn_bridge",
        "rome_colosseum",
        "dubai_burj_khalifa",
        "nyc_times_square",
        "barcelona_sagrada",
        "london_eye",
        "sydney_opera",
        "tokyo_tower",
        "sf_golden_gate",
        "athens_acropolis",
        "singapore_marina_bay",
        "venice_san_marco",
        "nyc_central_park",
        "london_big_ben",
        # travel expanded
        "airplane_window",
        "train_journey",
        "hotel_checkin",
        "hotel_breakfast",
        "sea_balcony",
        "old_town_walk",
        "street_market",
        # atmosphere
        "rainy_day",
        "night_coffee",
        "evening_home",
        # status & sport
        "car_exit",
        "travel_luxury",
        "yoga_outdoor",
        "cycling",
        "tinder_pack_rooftop_golden",
        "tinder_pack_minimal_studio",
        "tinder_pack_cafe_window",
    ],
    "cv": [
        "corporate",
        "boardroom",
        "formal_portrait",
        "startup_casual",
        "coworking",
        "standing_desk",
        "neutral",
        "tech_developer",
        "creative_director",
        "medical",
        "legal_finance",
        "architect",
        "speaker_stage",
        "podcast",
        "mentor",
        "outdoor_business",
        # career expanded
        "video_call",
        "glass_wall_pose",
        "analytics_review",
        "tablet_stylus",
        "notebook_ideas",
        "coffee_break_work",
        "late_hustle",
        # archetypes
        "digital_nomad",
        "intellectual",
        # moments
        "before_meeting",
        "business_lounge",
        "decision_moment",
        # Document format photos (document-photo scenario)
        "photo_3x4",
        "passport_rf",
        "visa_eu",
        "visa_us",
        "photo_4x6",
    ],
    "social": [
        "influencer_urban",
        "influencer_minimal",
        "luxury",
        "casual",
        "morning_routine",
        "fitness_lifestyle",
        "food_blogger",
        "travel_blogger",
        "artistic",
        "golden_hour",
        "neon_night",
        "vintage_film",
        "pastel_soft",
        "youtube_creator",
        "linkedin_premium",
        "tinder_top",
        "instagram_aesthetic",
        "podcast_host",
        # aesthetic
        "mirror_aesthetic",
        "elevator_clean",
        "shopfront",
        "candid_street",
        # hobbies
        "reading_home",
        "reading_cafe",
        "sketching",
        "photographer",
        "meditation",
        "online_learning",
        # sport social
        "cycling_social",
        # cinematic
        "panoramic_window",
        "in_motion",
        "architecture_shadow",
        "achievement_moment",
        # evening & mood
        "skyscraper_view",
        "after_work",
        "evening_planning",
        "focused_mood",
        "light_irony",
    ],
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
                cells.append(
                    MatrixCell(
                        scenario=scenario,
                        style=style,
                        level=lvl.level,
                        strength=lvl.strength,
                        steps=list(lvl.steps),
                    )
                )
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
        max_depth = len(styles) * len(LEVELS)
        if max_depth == 0:
            return 0.0
        return min(100.0, round(self.depth / max_depth * 100, 1))


def engagement_snapshot(
    user_id: int, mode: str, depth: int, current_style: str = ""
) -> EngagementSnapshot:
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


__all__ = [
    "EnhancementLevel",
    "LEVELS",
    "level_for_depth",
    "SCENARIO_STYLES",
    "styles_for_scenario",
    "MatrixCell",
    "build_full_matrix",
    "matrix_stats",
    "EngagementSnapshot",
    "engagement_snapshot",
]
