"""Humanize raw LLM scores to user-friendly X.XX values.

Shared by AnalysisPipeline and pre-analyze endpoint to avoid duplication.
"""
from __future__ import annotations

import hashlib

SCORE_KEYS = ("dating_score", "trust", "competence", "hireability", "social_score")
PERCEPTION_KEYS = ("warmth", "presence", "appeal")
SCORE_FLOOR = 5.0
PERCEPTION_FLOOR = 3.0


def humanize_score(raw: float, seed: str, floor: float = SCORE_FLOOR) -> float:
    """Convert raw 0-10 LLM score to X.XX with natural-feeling fractional part.

    Applies the given floor so users never see demoralisingly low numbers.
    """
    base = int(raw)
    raw_frac = raw - base
    h = int(hashlib.md5(seed.encode()).hexdigest()[:6], 16)
    frac = (h % 100) / 100.0
    if raw_frac > 0:
        frac = round(raw_frac + (frac - 0.5) * 0.1, 2)
    result = base + max(0.01, min(0.99, frac))
    result = max(floor, result)
    return round(min(9.99, result), 2)


def humanize_result_scores(result_dict: dict, seed_prefix: str) -> None:
    """In-place humanize all score and perception keys in a result dict."""
    for sk in SCORE_KEYS:
        if sk in result_dict and isinstance(result_dict[sk], (int, float)):
            result_dict[sk] = humanize_score(float(result_dict[sk]), f"{seed_prefix}:{sk}")

    ps = result_dict.get("perception_scores")
    if isinstance(ps, dict):
        for pk in PERCEPTION_KEYS:
            if pk in ps and isinstance(ps[pk], (int, float)):
                ps[pk] = humanize_score(float(ps[pk]), f"{seed_prefix}:p:{pk}", floor=PERCEPTION_FLOOR)
        result_dict["perception_scores"] = ps
    elif hasattr(ps, "model_dump"):
        ps_dict = ps.model_dump()
        for pk in PERCEPTION_KEYS:
            if pk in ps_dict and isinstance(ps_dict[pk], (int, float)):
                ps_dict[pk] = humanize_score(float(ps_dict[pk]), f"{seed_prefix}:p:{pk}", floor=PERCEPTION_FLOOR)
        result_dict["perception_scores"] = ps_dict
