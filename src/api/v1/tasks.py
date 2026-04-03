from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import Task, User
from src.models.enums import TaskStatus, AnalysisMode
from src.models.schemas import TaskResponse
from src.api.deps import get_db, get_current_user

router = APIRouter()


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
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

    return TaskResponse(
        task_id=task.id,
        status=TaskStatus(task.status),
        mode=AnalysisMode(task.mode),
        created_at=task.created_at,
        completed_at=task.completed_at,
        result=task.result,
        share_card_url=task.share_card_path,
        error_message=task.error_message,
    )
