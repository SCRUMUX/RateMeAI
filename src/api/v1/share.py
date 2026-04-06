from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, User
from src.models.enums import TaskStatus, AnalysisMode
from src.models.schemas import ShareResponse
from src.api.deps import get_db, get_auth_user
from src.providers.factory import get_storage

router = APIRouter()


def _bot_username() -> str:
    return settings.telegram_bot_username.lstrip("@")


@router.post("/{task_id}", response_model=ShareResponse)
async def create_share(
    task_id: uuid.UUID,
    user: User = Depends(get_auth_user),
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

    u = _bot_username()
    deep_link = f"https://t.me/{u}?start=ref_{user.id}"

    res = task.result or {}
    mode = AnalysisMode(task.mode)

    if mode == AnalysisMode.RATING:
        score = res.get("score", "?")
        caption = f"Мой рейтинг: {score}/10 — узнай свой → @{u}"
    elif mode == AnalysisMode.DATING:
        score = res.get("dating_score", "?")
        caption = f"Стиль для знакомств: {score}/10 — попробуй → @{u}"
    elif mode == AnalysisMode.CV:
        hire = res.get("hireability", "?")
        caption = f"Карьерный стиль: {hire}/10 — оцени своё фото → @{u}"
    elif mode == AnalysisMode.SOCIAL:
        score = res.get("social_score", "?")
        caption = f"Стиль для соцсетей: {score}/10 — попробуй → @{u}"
    else:
        caption = f"Мой эмодзи-пак — попробуй → @{u}"

    raw_card = task.share_card_path or ""
    image_url = ""
    if raw_card:
        if raw_card.startswith("http://") or raw_card.startswith("https://"):
            image_url = raw_card
        else:
            storage = get_storage()
            image_url = await storage.get_url(raw_card)

    gen_url = res.get("generated_image_url") or res.get("image_url")
    if not image_url and gen_url and (gen_url.startswith("http://") or gen_url.startswith("https://")):
        image_url = gen_url

    return ShareResponse(
        image_url=image_url,
        caption=caption,
        deep_link=deep_link,
    )
