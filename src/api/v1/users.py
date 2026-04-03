from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import User, UsageLog
from src.models.schemas import TelegramAuthRequest, UserResponse, UserUsage
from src.api.deps import get_db, get_current_user

router = APIRouter()


@router.post("/auth/telegram", response_model=UserResponse)
async def auth_telegram(
    body: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.telegram_id == body.telegram_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=body.telegram_id,
            username=body.username,
            first_name=body.first_name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    today = date.today()
    usage_result = await db.execute(
        select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.usage_date == today)
    )
    log = usage_result.scalar_one_or_none()
    used = log.count if log else 0
    limit = settings.rate_limit_daily if not user.is_premium else settings.rate_limit_daily * 10

    return UserResponse(
        user_id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        usage=UserUsage(
            daily_limit=limit,
            used=used,
            remaining=max(0, limit - used),
            is_premium=user.is_premium,
        ),
    )


@router.get("/users/me/usage", response_model=UserUsage)
async def get_my_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    result = await db.execute(
        select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.usage_date == today)
    )
    log = result.scalar_one_or_none()
    used = log.count if log else 0
    limit = settings.rate_limit_daily if not user.is_premium else settings.rate_limit_daily * 10

    return UserUsage(
        daily_limit=limit,
        used=used,
        remaining=max(0, limit - used),
        is_premium=user.is_premium,
    )
