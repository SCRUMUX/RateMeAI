"""Engagement analytics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request

from src.orchestrator.enhancement_matrix import matrix_stats, engagement_snapshot

router = APIRouter()


@router.get("/matrix")
async def get_matrix_stats():
    """Return enhancement matrix summary."""
    return matrix_stats()


@router.get("/depth/{telegram_id}")
async def get_user_depth(telegram_id: int, request: Request):
    """Return engagement depth for a user across all modes."""
    redis = request.app.state.redis
    modes = ["dating", "cv", "social"]
    result = {}
    for mode in modes:
        key = f"ratemeai:depth:{telegram_id}:{mode}"
        val = await redis.get(key)
        depth = int(val) if val else 0
        if depth > 0:
            snap = engagement_snapshot(telegram_id, mode, depth)
            result[mode] = {
                "depth": depth,
                "level": snap.level.name,
                "completion_pct": snap.completion_pct,
                "remaining_styles": snap.remaining_styles,
            }
    return {"telegram_id": telegram_id, "engagement": result}
