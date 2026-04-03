from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import Task, User
from src.models.enums import TaskStatus
from src.models.schemas import ShareResponse
from src.api.deps import get_db, get_current_user
from src.config import settings

router = APIRouter()


@router.post("/{task_id}", response_model=ShareResponse)
async def create_share(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if task.status != TaskStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Task not completed yet")

    score = task.result.get("score", "?") if task.result else "?"
    bot_username = "RateMeAIBot"
    deep_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    share_card_url = task.share_card_path or ""
    caption = f"Мой рейтинг: {score}/10 🔥 Узнай свой → @{bot_username}"

    return ShareResponse(
        image_url=share_card_url,
        caption=caption,
        deep_link=deep_link,
    )
