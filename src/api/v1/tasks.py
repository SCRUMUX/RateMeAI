from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, User
from src.models.enums import TaskStatus, AnalysisMode
from src.models.schemas import TaskResponse, TaskHistoryItem, TaskHistoryResponse
from src.api.deps import get_db, get_current_user

router = APIRouter()

_STORAGE_PATH_RE = re.compile(r"/storage/.+")


def _normalize_storage_url(url: str) -> str:
    """Rewrite any storage URL to use current api_base_url.

    Handles URLs stored in DB with outdated base (e.g. http://localhost:8000).
    """
    if not url:
        return ""
    m = _STORAGE_PATH_RE.search(url)
    if m:
        base = settings.api_base_url.rstrip("/")
        return f"{base}{m.group(0)}"
    if url.startswith("http"):
        return url
    base = settings.api_base_url.rstrip("/")
    return f"{base}/storage/{url.lstrip('/')}"


@router.get("", response_model=TaskHistoryResponse)
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List completed tasks that have a generated image (for the Storage gallery)."""
    base_q = (
        select(Task)
        .where(
            Task.user_id == user.id,
            Task.status == TaskStatus.COMPLETED.value,
        )
        .order_by(Task.completed_at.desc())
    )

    count_q = select(sa_func.count()).select_from(
        base_q.with_only_columns(Task.id).subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    rows = await db.execute(base_q.limit(limit).offset(offset))
    tasks = rows.scalars().all()

    items: list[TaskHistoryItem] = []
    for t in tasks:
        r = t.result or {}
        ctx = t.context or {}

        gen_url = r.get("generated_image_url") or r.get("image_url") or ""
        gen_url = _normalize_storage_url(gen_url)
        if not gen_url:
            gen_url = _normalize_storage_url(r.get("generated_image_path", ""))

        score_after = (
            r.get("dating_score")
            or r.get("social_score")
            or r.get("score")
        )
        score_before = r.get("score_before")
        ps = r.get("perception_scores")

        items.append(TaskHistoryItem(
            task_id=t.id,
            mode=t.mode,
            style=ctx.get("style", ""),
            completed_at=t.completed_at,
            input_image_url=_normalize_storage_url(t.input_image_path or ""),
            generated_image_url=gen_url,
            score_before=float(score_before) if score_before is not None else None,
            score_after=float(score_after) if score_after is not None else None,
            perception_scores=ps if isinstance(ps, dict) else None,
        ))

    return TaskHistoryResponse(items=items, total_count=total)


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
