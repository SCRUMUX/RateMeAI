from __future__ import annotations

from datetime import date
from typing import AsyncGenerator

from fastapi import Request, Depends, HTTPException, Header
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import User, UsageLog, ApiClient
from src.utils.auth_tokens import hash_api_key


def _pepper() -> str:
    val = settings.api_key_pepper or settings.admin_secret
    if not val and settings.is_production:
        raise RuntimeError("API_KEY_PEPPER must be set in production")
    return val or "dev-pepper"


def _rate_limit_exempt_usernames() -> set[str]:
    raw = (settings.rate_limit_exempt_usernames or "").strip()
    if not raw:
        return set()
    return {
        p.strip().lstrip("@").lower()
        for p in raw.split(",")
        if p.strip()
    }


def _user_exempt_from_rate_limit(user: User) -> bool:
    if not user.username:
        return False
    uname = user.username.strip().lstrip("@").lower()
    return uname in _rate_limit_exempt_usernames()


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.db_sessionmaker() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_auth_user(
    x_telegram_id: int | None = Header(None, alias="X-Telegram-Id"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if x_api_key:
        h = hash_api_key(x_api_key.strip(), _pepper())
        r = await db.execute(
            select(ApiClient).where(ApiClient.key_hash == h, ApiClient.is_active.is_(True))
        )
        client = r.scalar_one_or_none()
        if client is None:
            raise HTTPException(status_code=401, detail="Invalid or inactive API key")
        user = await db.get(User, client.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user

    if x_telegram_id is not None:
        result = await db.execute(select(User).where(User.telegram_id == x_telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="User not found. Register via /auth/telegram first.",
            )
        return user

    raise HTTPException(status_code=401, detail="Provide X-Telegram-Id or X-API-Key header")


async def get_current_user(user: User = Depends(get_auth_user)) -> User:
    return user


async def check_rate_limit(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if _user_exempt_from_rate_limit(user):
        return user

    r = await db.execute(select(ApiClient).where(ApiClient.user_id == user.id).limit(1))
    api_client = r.scalar_one_or_none()

    if api_client is not None:
        limit = api_client.rate_limit_daily
    else:
        base = settings.rate_limit_daily
        limit = base * 10 if user.is_premium else base

    today = date.today()
    result = await db.execute(
        select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.usage_date == today)
    )
    log = result.scalar_one_or_none()
    used = log.count if log else 0

    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached ({limit}). Try again tomorrow or upgrade to premium.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "86400",
            },
        )
    user._rate_limit_info = {"limit": limit, "remaining": limit - used - 1}
    return user
