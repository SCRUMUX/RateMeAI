from __future__ import annotations

from datetime import date
from typing import AsyncGenerator

from fastapi import Request, Depends, HTTPException, Header
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import User, UsageLog


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.db_sessionmaker() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_current_user(
    x_telegram_id: int = Header(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(select(User).where(User.telegram_id == x_telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found. Register via /auth/telegram first.")
    return user


async def check_rate_limit(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    today = date.today()
    result = await db.execute(
        select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.usage_date == today)
    )
    log = result.scalar_one_or_none()
    used = log.count if log else 0
    limit = settings.rate_limit_daily if not user.is_premium else settings.rate_limit_daily * 10

    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached ({limit}). Try again tomorrow or upgrade to premium.",
        )
    return user
