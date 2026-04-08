"""Shared utilities for extracting perception scores from LLM output."""
from __future__ import annotations

from src.models.schemas import PerceptionScores, PerceptionInsight

CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "dating": {"warmth": 0.35, "appeal": 0.35, "presence": 0.20, "authenticity": 0.10},
    "cv":     {"warmth": 0.25, "presence": 0.40, "appeal": 0.15, "authenticity": 0.20},
    "social": {"warmth": 0.20, "appeal": 0.40, "presence": 0.30, "authenticity": 0.10},
    "rating": {"warmth": 0.33, "appeal": 0.34, "presence": 0.33, "authenticity": 0.00},
}


def extract_perception_scores(raw: dict) -> PerceptionScores:
    """Extract perception_scores from LLM output with safe defaults."""
    ps = raw.get("perception_scores", {})
    return PerceptionScores(
        warmth=_safe_float(ps.get("warmth"), 5.0),
        presence=_safe_float(ps.get("presence"), 5.0),
        appeal=_safe_float(ps.get("appeal"), 5.0),
        authenticity=9.0,
    )


def extract_perception_insights(raw: dict) -> list[PerceptionInsight]:
    """Extract perception_insights from LLM output, validating each entry."""
    raw_insights = raw.get("perception_insights", [])
    if not isinstance(raw_insights, list):
        return []

    results = []
    for item in raw_insights[:3]:
        if not isinstance(item, dict):
            continue
        try:
            results.append(PerceptionInsight(
                parameter=str(item.get("parameter", "appeal")),
                current_level=str(item.get("current_level", "solid_base")),
                suggestion=str(item.get("suggestion", "")),
                controllable_by=str(item.get("controllable_by", "lighting")),
            ))
        except Exception:
            continue

    return results


def compute_composite_score(perception: PerceptionScores, mode: str) -> float:
    """Compute a weighted composite score from perception parameters."""
    weights = CATEGORY_WEIGHTS.get(mode, CATEGORY_WEIGHTS["rating"])
    score = (
        perception.warmth * weights["warmth"]
        + perception.presence * weights.get("presence", 0.33)
        + perception.appeal * weights.get("appeal", 0.34)
        + perception.authenticity * weights.get("authenticity", 0.0)
    )
    return round(min(10.0, max(0.0, score)), 2)


def _safe_float(val, default: float) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return max(0.0, min(10.0, f))
    except (TypeError, ValueError):
        return default
