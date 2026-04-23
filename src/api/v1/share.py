from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import Task, User
from src.models.enums import TaskStatus
from src.models.schemas import ShareResponse
from src.api.deps import get_db, get_auth_user
from src.providers.factory import get_storage
from src.channels.deep_links import (
    build_deep_link,
    build_share_caption,
    PROVIDER_TELEGRAM,
)

router = APIRouter()


@router.post("/{task_id}", response_model=ShareResponse)
async def create_share(
    task_id: uuid.UUID,
    channel: str = Query(
        PROVIDER_TELEGRAM, description="Source channel: telegram, ok, vk, web"
    ),
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

    res = task.result or {}
    deep_link = build_deep_link(str(user.id), channel)
    caption = build_share_caption(res, channel)

    raw_card = task.share_card_path or ""
    image_url = ""
    if raw_card:
        if raw_card.startswith("http://") or raw_card.startswith("https://"):
            image_url = raw_card
        else:
            storage = get_storage()
            image_url = await storage.get_url(raw_card)

    gen_url = res.get("generated_image_url") or res.get("image_url")
    if (
        not image_url
        and gen_url
        and (gen_url.startswith("http://") or gen_url.startswith("https://"))
    ):
        image_url = gen_url

    return ShareResponse(
        image_url=image_url,
        caption=caption,
        deep_link=deep_link,
    )
