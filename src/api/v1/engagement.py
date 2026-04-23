"""Engagement analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.api.deps import get_auth_user
from src.models.db import User
from src.orchestrator.enhancement_matrix import matrix_stats, engagement_snapshot

router = APIRouter()


@router.get("/matrix")
async def get_matrix_stats():
    """Return enhancement matrix summary."""
    return matrix_stats()


@router.get("/depth/me")
async def get_my_depth(
    request: Request,
    user: User = Depends(get_auth_user),
):
    """Return engagement depth for the authenticated user across all modes."""
    redis = request.app.state.redis
    user_id = str(user.id)
    modes = ["dating", "cv", "social"]
    result = {}
    for mode in modes:
        # Try new user_id-based key first, fall back to telegram_id for backward compat
        key = f"ratemeai:depth:{user_id}:{mode}"
        val = await redis.get(key)
        if val is None and user.telegram_id:
            val = await redis.get(f"ratemeai:depth:{user.telegram_id}:{mode}")
        depth = int(val) if val else 0
        if depth > 0:
            snap = engagement_snapshot(user.telegram_id or 0, mode, depth)
            result[mode] = {
                "depth": depth,
                "level": snap.level.name,
                "completion_pct": snap.completion_pct,
                "remaining_styles": snap.remaining_styles,
            }
    return {"user_id": user_id, "engagement": result}


@router.get("/depth/{telegram_id}")
async def get_user_depth(
    telegram_id: int,
    request: Request,
    _user: User = Depends(get_auth_user),
):
    """Legacy: Return engagement depth by telegram_id (backward compat for bot)."""
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
