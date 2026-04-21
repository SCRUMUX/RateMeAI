from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy import select, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import Task, User, CreditTransaction
from src.models.enums import TaskStatus, AnalysisMode
from src.models.schemas import TaskResponse, TaskHistoryItem, TaskHistoryResponse
from src.api.deps import get_db, get_current_user, get_redis
from src.services.task_contract import get_market_id
from src.utils.redis_keys import gen_image_cache_keys

router = APIRouter()

_storage_dir = Path(settings.storage_local_path).resolve()

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


def _extract_history_score_after(result: dict, mode: str) -> float | None:
    """Pick the post-generation score for the storage history UI.

    Preference order:
      1. Explicit `score_after` field (written by `DeltaScorer` on new runs).
      2. `delta.<mode_key>.post` — defensive path for tasks where
         `DeltaScorer` populated the delta dict but not the flat fields
         (legacy rows, partial regressions).
      3. Flat scalar fields (`dating_score` / `social_score` / `score`,
         or the average of `trust/competence/hireability` for CV) —
         final fallback for very old rows predating delta scoring.
    """
    delta_map = result.get("delta") or {}
    score_after = result.get("score_after")
    if score_after is None and delta_map:
        if mode == "dating" and isinstance(delta_map.get("dating_score"), dict):
            score_after = delta_map["dating_score"].get("post")
        elif mode == "social" and isinstance(delta_map.get("social_score"), dict):
            score_after = delta_map["social_score"].get("post")
        elif mode == "cv":
            cv_post_vals = [
                float(delta_map[k]["post"])
                for k in ("trust", "competence", "hireability")
                if isinstance(delta_map.get(k), dict) and delta_map[k].get("post") is not None
            ]
            if cv_post_vals:
                score_after = round(sum(cv_post_vals) / len(cv_post_vals), 2)
    if score_after is None:
        score_after = result.get("dating_score") or result.get("social_score") or result.get("score")
    if score_after is None and mode == "cv":
        cv_vals = [
            float(result[k])
            for k in ("trust", "competence", "hireability")
            if result.get(k) is not None
        ]
        if cv_vals:
            score_after = round(sum(cv_vals) / len(cv_vals), 2)
    return float(score_after) if score_after is not None else None


async def _image_available(task: Task, redis: Redis) -> bool:
    """Check whether generated image data is still reachable."""
    r = task.result or {}

    if r.get("_purged_at"):
        return False

    # 1. local file
    for key in ("generated_image_url", "image_url", "generated_image_path"):
        raw = r.get(key, "")
        if not raw:
            continue
        m = _STORAGE_PATH_RE.search(raw)
        if m:
            file_path = m.group(0).split("/storage/", 1)[-1]
            if (_storage_dir / file_path).resolve().is_file():
                return True

    # 2. Redis cache
    market_id = get_market_id(task.context, fallback=settings.resolved_market_id)
    for cache_key in gen_image_cache_keys(str(task.id), market_id):
        if await redis.exists(cache_key):
            return True

    # 3. DB base64 fallback
    if r.get("generated_image_b64"):
        return True

    return False


@router.get("", response_model=TaskHistoryResponse)
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List completed tasks that have a generated image (for the Storage gallery).

    Counter (``total_count``) и список ``items`` должны идти вровень: если задача
    закрылась без картинки (Reve / moderation / ошибка), её нельзя учитывать —
    иначе счётчик хранилища растёт, а галерея пуста (и пользователь пугается,
    думая что его фото пропало). Мы фильтруем COMPLETED-задачи по флагу
    ``result.has_generated_image`` (его выставляет worker на финальном шаге)
    и по ``_image_available`` (чтобы не показывать файлы, подчищенные TTL).
    """
    # Отфильтровываем tasks, у которых нет сгенерированного URL/пути. Используем
    # CAST(... AS VARCHAR) — это работает и для sqlalchemy.JSON, и для JSONB, в
    # отличие от диалект-специфичного .astext. Старые записи без маркера
    # has_generated_image тоже попадут, если у них есть любой из трёх URL-ключей
    # в result.
    gen_url_filter = (
        cast(Task.result["generated_image_url"], String).isnot(None)
        | cast(Task.result["image_url"], String).isnot(None)
        | cast(Task.result["generated_image_path"], String).isnot(None)
    )
    count_q = (
        select(func.count(Task.id))
        .where(
            Task.user_id == user.id,
            Task.status == TaskStatus.COMPLETED.value,
            gen_url_filter,
        )
    )
    total_count = (await db.execute(count_q)).scalar() or 0

    base_q = (
        select(Task)
        .where(
            Task.user_id == user.id,
            Task.status == TaskStatus.COMPLETED.value,
            gen_url_filter,
        )
        .order_by(Task.completed_at.desc())
    )

    rows = await db.execute(base_q.limit(limit * 3).offset(offset))
    tasks = rows.scalars().all()

    items: list[TaskHistoryItem] = []
    for t in tasks:
        if not await _image_available(t, redis):
            continue

        r = t.result or {}
        ctx = t.context or {}

        gen_url = r.get("generated_image_url") or r.get("image_url") or ""
        gen_url = _normalize_storage_url(gen_url)
        if not gen_url:
            gen_url = _normalize_storage_url(r.get("generated_image_path", ""))

        score_after = _extract_history_score_after(r, t.mode)
        score_before = r.get("score_before")
        ps = r.get("perception_scores")

        items.append(TaskHistoryItem(
            task_id=t.id,
            mode=t.mode,
            style=ctx.get("style", ""),
            completed_at=t.completed_at,
            # Privacy: original photo is never exposed to clients — deleted after preprocessing.
            input_image_url="",
            generated_image_url=gen_url,
            score_before=float(score_before) if score_before is not None else None,
            score_after=float(score_after) if score_after is not None else None,
            perception_scores=ps if isinstance(ps, dict) else None,
            purged=bool(r.get("_purged_at")),
        ))

        if len(items) >= limit:
            break

    return TaskHistoryResponse(items=items, total_count=total_count)


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

    result_view = dict(task.result) if task.result else None
    if result_view is not None:
        for k in ("input_image_url", "input_image_path", "original_image_url"):
            if k in result_view:
                result_view[k] = None
        if result_view.get("_purged_at"):
            for k in ("generated_image_url", "image_url", "generated_image_path", "generated_image_b64"):
                if k in result_view:
                    result_view[k] = None
            result_view["purged"] = True

    share_card = task.share_card_path
    if result_view and result_view.get("_purged_at"):
        share_card = None

    return TaskResponse(
        task_id=task.id,
        status=TaskStatus(task.status),
        mode=AnalysisMode(task.mode),
        created_at=task.created_at,
        completed_at=task.completed_at,
        result=result_view,
        share_card_url=share_card,
        error_message=task.error_message,
    )


@router.post("/{task_id}/refund")
async def refund_unreachable_image(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Refund 1 credit when a completed task's generated image is unreachable.

    Guards:
    - task must belong to the requesting user
    - task must be COMPLETED with credit_pre_reserved
    - credit must not have been already refunded for this task
    - generated image must be genuinely unreachable (disk / Redis / DB b64)
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if task.status != TaskStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="Task is not completed")

    ctx = task.context or {}
    r = task.result or {}

    if not ctx.get("credit_pre_reserved"):
        raise HTTPException(status_code=409, detail="No credit was reserved for this task")
    if r.get("credit_refunded"):
        raise HTTPException(status_code=409, detail="Credit already refunded for this task")

    if await _image_available(task, redis):
        raise HTTPException(status_code=409, detail="Image is still available — no refund needed")

    fresh = await db.execute(
        select(User).where(User.id == user.id).with_for_update()
    )
    fresh_user = fresh.scalar_one()

    fresh_user.image_credits += 1
    r["credit_refunded"] = True
    r["credit_deducted"] = False
    task.result = r
    db.add(CreditTransaction(
        user_id=user.id,
        amount=1,
        balance_after=fresh_user.image_credits,
        tx_type="refund_image_unreachable",
    ))

    await db.commit()

    return {"status": "refunded", "balance": fresh_user.image_credits}
