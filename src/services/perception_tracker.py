"""Perception Tracker — persists best perception scores per user/mode/style.

Only updates a record when the new scores exceed the stored best,
enabling "personal best" gamification and progress comparison.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import UserPerceptionRecord

logger = logging.getLogger(__name__)


async def update_best_scores(
    session: AsyncSession,
    user_id: str,
    mode: str,
    style: str,
    perception_scores: dict,
) -> bool:
    """Upsert the user's best perception scores for a mode/style combination.

    Returns True if a record was updated (new personal best), False otherwise.
    """
    import uuid as _uuid

    try:
        uid = _uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        logger.warning("Invalid user_id for perception tracking: %s", user_id)
        return False

    warmth = float(perception_scores.get("warmth", 0))
    presence = float(perception_scores.get("presence", 0))
    appeal = float(perception_scores.get("appeal", 0))
    authenticity = float(perception_scores.get("authenticity", 9.0))

    stmt = select(UserPerceptionRecord).where(
        UserPerceptionRecord.user_id == uid,
        UserPerceptionRecord.mode == mode,
        UserPerceptionRecord.style == (style or "default"),
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        record = UserPerceptionRecord(
            user_id=uid,
            mode=mode,
            style=style or "default",
            warmth=warmth,
            presence=presence,
            appeal=appeal,
            authenticity=authenticity,
        )
        session.add(record)
        await session.flush()
        logger.info("Created perception record user=%s mode=%s style=%s", user_id, mode, style)
        return True

    updated = False
    if warmth > record.warmth:
        record.warmth = warmth
        updated = True
    if presence > record.presence:
        record.presence = presence
        updated = True
    if appeal > record.appeal:
        record.appeal = appeal
        updated = True
    if authenticity > record.authenticity:
        record.authenticity = authenticity
        updated = True

    if updated:
        await session.flush()
        logger.info("Updated perception best for user=%s mode=%s style=%s", user_id, mode, style)

    return updated


async def get_best_scores(
    session: AsyncSession,
    user_id: str,
    mode: str | None = None,
) -> list[dict]:
    """Retrieve best perception scores for a user, optionally filtered by mode."""
    import uuid as _uuid

    try:
        uid = _uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return []

    stmt = select(UserPerceptionRecord).where(UserPerceptionRecord.user_id == uid)
    if mode:
        stmt = stmt.where(UserPerceptionRecord.mode == mode)
    stmt = stmt.order_by(UserPerceptionRecord.updated_at.desc())

    result = await session.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "mode": r.mode,
            "style": r.style,
            "warmth": r.warmth,
            "presence": r.presence,
            "appeal": r.appeal,
            "authenticity": r.authenticity,
        }
        for r in records
    ]
