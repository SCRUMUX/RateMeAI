from __future__ import annotations

import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import User, UsageLog, ApiClient
from src.models.schemas import (
    TelegramAuthRequest,
    UserResponse,
    UserUsage,
    ApiClientCreateRequest,
    ApiClientCreatedResponse,
)
from src.api.deps import get_db, get_auth_user
from src.utils.auth_tokens import hash_api_key

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
    elif body.username and user.username != body.username:
        user.username = body.username
        if body.first_name is not None:
            user.first_name = body.first_name
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


@router.post("/auth/api-client", response_model=ApiClientCreatedResponse)
async def create_api_client(
    body: ApiClientCreateRequest,
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
    db: AsyncSession = Depends(get_db),
):
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    raw_key = secrets.token_urlsafe(32)
    pepper = settings.api_key_pepper or settings.admin_secret or "dev-pepper"

    user = User(
        telegram_id=None,
        username=f"api_{body.name}",
        first_name=None,
    )
    db.add(user)
    await db.flush()

    client = ApiClient(
        name=body.name,
        key_hash=hash_api_key(raw_key, pepper),
        user_id=user.id,
        rate_limit_daily=body.rate_limit_daily,
    )
    db.add(client)
    await db.commit()
    await db.refresh(user)
    await db.refresh(client)

    return ApiClientCreatedResponse(
        api_key=raw_key,
        user_id=user.id,
        client_id=client.id,
    )


@router.get("/users/me/usage", response_model=UserUsage)
async def get_my_usage(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    result = await db.execute(
        select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.usage_date == today)
    )
    log = result.scalar_one_or_none()
    used = log.count if log else 0

    ac = await db.execute(select(ApiClient).where(ApiClient.user_id == user.id).limit(1))
    api_client = ac.scalar_one_or_none()
    if api_client is not None:
        limit = api_client.rate_limit_daily
    else:
        limit = settings.rate_limit_daily if not user.is_premium else settings.rate_limit_daily * 10

    return UserUsage(
        daily_limit=limit,
        used=used,
        remaining=max(0, limit - used),
        is_premium=user.is_premium,
    )
