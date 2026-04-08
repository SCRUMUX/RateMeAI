from __future__ import annotations

import logging
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import User, UsageLog, ApiClient, UserIdentity
from src.models.schemas import (
    TelegramAuthRequest,
    UserResponse,
    UserUsage,
    ApiClientCreateRequest,
    ApiClientCreatedResponse,
    ChannelAuthResponse,
    OKAuthRequest,
    VKAuthRequest,
    WebAuthRequest,
)
from src.api.deps import get_db, get_auth_user, get_redis
from src.utils.auth_tokens import hash_api_key
from src.services.sessions import create_session

logger = logging.getLogger(__name__)
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


# ------------------------------------------------------------------
# Multi-channel auth helpers
# ------------------------------------------------------------------

async def _find_or_create_by_identity(
    db: AsyncSession,
    provider: str,
    external_id: str,
    display_name: str | None = None,
) -> User:
    """Lookup user by (provider, external_id). Create User + UserIdentity if new."""
    result = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.external_id == external_id,
        )
    )
    identity = result.scalar_one_or_none()

    if identity is not None:
        user = await db.get(User, identity.user_id)
        if user is None:
            raise HTTPException(status_code=500, detail="Orphan identity record")
        return user

    user = User(username=display_name, first_name=display_name)
    db.add(user)
    await db.flush()

    db.add(UserIdentity(
        user_id=user.id,
        provider=provider,
        external_id=external_id,
    ))
    await db.commit()
    await db.refresh(user)
    return user


async def _usage_for(user: User, db: AsyncSession) -> UserUsage:
    today = date.today()
    r = await db.execute(
        select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.usage_date == today)
    )
    log = r.scalar_one_or_none()
    used = log.count if log else 0
    limit = settings.rate_limit_daily if not user.is_premium else settings.rate_limit_daily * 10
    return UserUsage(
        daily_limit=limit,
        used=used,
        remaining=max(0, limit - used),
        is_premium=user.is_premium,
    )


async def _auth_response(user: User, db: AsyncSession, redis: Redis) -> ChannelAuthResponse:
    token = await create_session(redis, user.id)
    usage = await _usage_for(user, db)
    return ChannelAuthResponse(session_token=token, user_id=user.id, usage=usage)


# ------------------------------------------------------------------
# OK auth
# ------------------------------------------------------------------

@router.post("/auth/ok", response_model=ChannelAuthResponse)
async def auth_ok(
    body: OKAuthRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    from src.channels.ok_auth import verify_ok_auth_sig

    if not verify_ok_auth_sig(body.logged_user_id, body.session_key, body.auth_sig):
        raise HTTPException(status_code=401, detail="Invalid OK auth_sig")

    user = await _find_or_create_by_identity(db, "ok", body.logged_user_id)
    return await _auth_response(user, db, redis)


# ------------------------------------------------------------------
# VK auth
# ------------------------------------------------------------------

@router.post("/auth/vk", response_model=ChannelAuthResponse)
async def auth_vk(
    body: VKAuthRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    from src.channels.vk_auth import verify_vk_launch_params

    vk_user_id = verify_vk_launch_params(body.launch_params)
    if vk_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid VK launch params signature")

    user = await _find_or_create_by_identity(db, "vk", vk_user_id)
    return await _auth_response(user, db, redis)


# ------------------------------------------------------------------
# Web (anonymous / device-based) auth
# ------------------------------------------------------------------

@router.post("/auth/web", response_model=ChannelAuthResponse)
async def auth_web(
    body: WebAuthRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    user = await _find_or_create_by_identity(db, "web", body.device_id)
    return await _auth_response(user, db, redis)
