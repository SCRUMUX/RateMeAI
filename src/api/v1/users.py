from __future__ import annotations

import logging
import secrets
import string
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.db import User, UsageLog, ApiClient, UserIdentity
from src.models.schemas import (
    TelegramAuthRequest,
    UserUsage,
    ApiClientCreateRequest,
    ApiClientCreatedResponse,
    ChannelAuthResponse,
    OKAuthRequest,
    VKAuthRequest,
    WebAuthRequest,
    OAuthInitRequest,
    OAuthInitResponse,
    LinkedIdentity,
    UserIdentitiesResponse,
    PhoneOTPRequestBody,
    PhoneOTPVerifyBody,
    LinkTokenResponse,
    ClaimLinkRequest,
    ClaimLinkResponse,
)
from src.api.deps import get_db, get_auth_user, get_redis
from src.utils.auth_tokens import hash_api_key
from src.services.sessions import create_session

logger = logging.getLogger(__name__)
router = APIRouter()

_LINK_TOKEN_PREFIX = "ratemeai:link_token:"
_LINK_TOKEN_TTL = 600  # 10 minutes
_LINK_TOKEN_LENGTH = 6


async def _resolve_link_code(redis: Redis, link_code: str) -> str | None:
    """Peek at link code → user_id without consuming it (consumed on claim)."""
    if not link_code:
        return None
    key = f"{_LINK_TOKEN_PREFIX}{link_code.upper().strip()}"
    raw = await redis.get(key)
    return raw if raw is None else (raw.decode() if isinstance(raw, bytes) else raw)


# ------------------------------------------------------------------
# Universal identity helper
# ------------------------------------------------------------------

async def _find_or_create_by_identity(
    db: AsyncSession,
    provider: str,
    external_id: str,
    display_name: str | None = None,
    profile_data: dict | None = None,
    *,
    link_to_user: User | None = None,
) -> User:
    """Single path for all identity resolution.

    - link_to_user=None  → find existing or register new user (login / register)
    - link_to_user=<User> → attach identity to that user (link mode);
      409 if identity already belongs to a *different* user.
    """
    result = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.external_id == external_id,
        )
    )
    identity = result.scalar_one_or_none()

    if identity is not None:
        owner = await db.get(User, identity.user_id)
        if owner is None:
            raise HTTPException(status_code=500, detail="Orphan identity record")

        if link_to_user is not None and identity.user_id != link_to_user.id:
            raise HTTPException(
                status_code=409,
                detail=f"This {provider} account is already linked to another user",
            )

        if profile_data and identity.profile_data != profile_data:
            identity.profile_data = profile_data
            await db.commit()
        return owner

    if link_to_user is not None:
        db.add(UserIdentity(
            user_id=link_to_user.id,
            provider=provider,
            external_id=external_id,
            profile_data=profile_data,
        ))
        if display_name and not link_to_user.username:
            link_to_user.username = display_name
        if display_name and not link_to_user.first_name:
            link_to_user.first_name = display_name
        await db.commit()
        await db.refresh(link_to_user)
        return link_to_user

    user = User(username=display_name, first_name=display_name)
    db.add(user)
    await db.flush()

    db.add(UserIdentity(
        user_id=user.id,
        provider=provider,
        external_id=external_id,
        profile_data=profile_data,
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


async def _identities_list(db: AsyncSession, user_id) -> list[LinkedIdentity]:
    result = await db.execute(
        select(UserIdentity).where(UserIdentity.user_id == user_id)
    )
    return [
        LinkedIdentity(
            provider=i.provider,
            external_id=i.external_id,
            profile_data=i.profile_data,
            created_at=i.created_at,
        )
        for i in result.scalars().all()
    ]


# ------------------------------------------------------------------
# Telegram auth (identity-first, no legacy fallback)
# ------------------------------------------------------------------

def _verify_telegram_init_data(init_data: str, bot_token: str) -> int | None:
    """Validate Telegram WebApp init_data hash. Returns telegram user id or None."""
    import hashlib
    import hmac
    import json as _json
    from urllib.parse import parse_qs

    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.pop("hash", [None])[0]
    if not received_hash:
        return None

    items = sorted(
        (k, v[0]) for k, v in parsed.items()
    )
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    user_data_raw = parsed.get("user", [None])[0]
    if not user_data_raw:
        return None
    try:
        user_data = _json.loads(user_data_raw)
        return int(user_data["id"])
    except (ValueError, KeyError, TypeError):
        return None


@router.post("/auth/telegram", response_model=ChannelAuthResponse)
async def auth_telegram(
    body: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    if body.init_data:
        bot_token = settings.telegram_bot_token
        if not bot_token:
            raise HTTPException(status_code=500, detail="Bot token not configured")
        verified_id = _verify_telegram_init_data(body.init_data, bot_token)
        if verified_id is None:
            raise HTTPException(status_code=401, detail="Invalid Telegram init_data signature")
        if verified_id != body.telegram_id:
            raise HTTPException(status_code=401, detail="Telegram ID mismatch")

    tg_id_str = str(body.telegram_id)
    user = await _find_or_create_by_identity(
        db, "telegram", tg_id_str,
        display_name=body.username or body.first_name,
        profile_data={"username": body.username, "first_name": body.first_name},
    )

    if body.username and user.username != body.username:
        user.username = body.username
        if body.first_name is not None:
            user.first_name = body.first_name
        await db.commit()
        await db.refresh(user)

    return await _auth_response(user, db, redis)


# ------------------------------------------------------------------
# API client (admin)
# ------------------------------------------------------------------

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

    user = User(username=f"api_{body.name}", first_name=None)
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


# ------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------

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

    return UserUsage(
        daily_limit=0,
        used=used,
        remaining=user.image_credits,
        is_premium=user.is_premium,
    )


# ------------------------------------------------------------------
# OK auth
# ------------------------------------------------------------------

@router.post("/auth/ok", response_model=ChannelAuthResponse)
async def auth_ok(
    body: OKAuthRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    if settings.is_edge and not settings.ok_app_secret_key.strip():
        raise HTTPException(status_code=503, detail="OK Mini App auth not configured on this server")

    from src.channels.ok_auth import verify_ok_auth_sig

    if not verify_ok_auth_sig(body.logged_user_id, body.session_key, body.auth_sig):
        raise HTTPException(status_code=401, detail="Invalid OK auth_sig")

    user = await _find_or_create_by_identity(db, "ok", body.logged_user_id)
    return await _auth_response(user, db, redis)


# ------------------------------------------------------------------
# VK auth (mini app)
# ------------------------------------------------------------------

@router.post("/auth/vk", response_model=ChannelAuthResponse)
async def auth_vk(
    body: VKAuthRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    if settings.is_edge and not settings.vk_app_secret.strip():
        raise HTTPException(status_code=503, detail="VK Mini App auth not configured on this server")

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


# ------------------------------------------------------------------
# Yandex ID OAuth
# ------------------------------------------------------------------

@router.post("/auth/yandex/init", response_model=OAuthInitResponse)
async def yandex_oauth_init(
    body: OAuthInitRequest,
    redis: Redis = Depends(get_redis),
):
    from src.channels.yandex_auth import build_authorize_url
    from src.services.oauth_state import save_oauth_state

    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/yandex/callback"

    link_user_id = await _resolve_link_code(redis, body.link_code)

    await save_oauth_state(
        redis, state,
        provider="yandex",
        device_id=body.device_id,
        link_user_id=link_user_id,
    )

    url = build_authorize_url(state, redirect_uri)
    return OAuthInitResponse(authorize_url=url)


@router.get("/auth/yandex/callback")
async def yandex_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    from src.channels.yandex_auth import exchange_code, get_user_info
    from src.services.oauth_state import pop_oauth_state
    from fastapi.responses import RedirectResponse

    stored = await pop_oauth_state(redis, state)
    if stored is None or stored.get("provider") != "yandex":
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    redirect_uri = f"{settings.api_base_url}/api/v1/auth/yandex/callback"
    access_token = await exchange_code(code, redirect_uri)
    if not access_token:
        raise HTTPException(status_code=401, detail="Yandex token exchange failed")

    yandex_user = await get_user_info(access_token)
    if yandex_user is None or not yandex_user.id:
        raise HTTPException(status_code=401, detail="Failed to fetch Yandex user info")

    link_user_id = stored.get("link_user_id")
    link_to = None
    if link_user_id:
        import uuid as _uuid
        link_to = await db.get(User, _uuid.UUID(link_user_id))

    user = await _find_or_create_by_identity(
        db, "yandex", yandex_user.id,
        display_name=yandex_user.display_name,
        profile_data={
            "login": yandex_user.login,
            "display_name": yandex_user.display_name,
            "email": yandex_user.default_email,
        },
        link_to_user=link_to,
    )
    token = await create_session(redis, user.id)

    web_base = settings.web_base_url or settings.api_base_url
    return RedirectResponse(
        url=f"{web_base}/auth/callback?token={token}&provider=yandex&user_id={user.id}",
    )


# ------------------------------------------------------------------
# Google OAuth
# ------------------------------------------------------------------

@router.post("/auth/google/init", response_model=OAuthInitResponse)
async def google_oauth_init(
    body: OAuthInitRequest,
    redis: Redis = Depends(get_redis),
):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured on this server")

    from src.channels.google_auth import build_authorize_url
    from src.services.oauth_state import save_oauth_state

    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/google/callback"

    link_user_id = await _resolve_link_code(redis, body.link_code)

    await save_oauth_state(
        redis, state,
        provider="google",
        device_id=body.device_id,
        link_user_id=link_user_id,
    )

    url = build_authorize_url(state, redirect_uri)
    return OAuthInitResponse(authorize_url=url)


@router.get("/auth/google/callback")
async def google_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    from src.channels.google_auth import exchange_code, get_user_info
    from src.services.oauth_state import pop_oauth_state
    from fastapi.responses import RedirectResponse

    web_base = settings.web_base_url or settings.api_base_url

    if error:
        return RedirectResponse(
            url=f"{web_base}/auth/callback?error={error}&error_description={error_description}&provider=google",
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{web_base}/auth/callback?error=missing_params&error_description=Missing+code+or+state&provider=google",
        )

    stored = await pop_oauth_state(redis, state)
    if stored is None or stored.get("provider") != "google":
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    redirect_uri = f"{settings.api_base_url}/api/v1/auth/google/callback"
    access_token = await exchange_code(code, redirect_uri)
    if not access_token:
        raise HTTPException(status_code=401, detail="Google token exchange failed")

    google_user = await get_user_info(access_token)
    if google_user is None or not google_user.id:
        raise HTTPException(status_code=401, detail="Failed to fetch Google user info")

    link_user_id = stored.get("link_user_id")
    link_to = None
    if link_user_id:
        import uuid as _uuid
        link_to = await db.get(User, _uuid.UUID(link_user_id))

    user = await _find_or_create_by_identity(
        db, "google", google_user.id,
        display_name=google_user.name,
        profile_data={
            "email": google_user.email,
            "name": google_user.name,
            "picture": google_user.picture,
        },
        link_to_user=link_to,
    )
    token = await create_session(redis, user.id)

    web_base = settings.web_base_url or settings.api_base_url
    return RedirectResponse(
        url=f"{web_base}/auth/callback?token={token}&provider=google&user_id={user.id}",
    )


# ------------------------------------------------------------------
# VK ID OAuth
# ------------------------------------------------------------------

@router.post("/auth/vk-id/init", response_model=OAuthInitResponse)
async def vk_id_oauth_init(
    body: OAuthInitRequest,
    redis: Redis = Depends(get_redis),
):
    if settings.is_edge and (
        not settings.vk_id_app_id.strip() or not settings.vk_id_app_secret.strip()
    ):
        raise HTTPException(status_code=503, detail="VK ID OAuth not configured on this server")

    from src.channels.vk_id_auth import build_authorize_url
    from src.services.oauth_state import generate_pkce, save_oauth_state

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/vk-id/callback"
    device_id = body.device_id or secrets.token_urlsafe(16)

    link_user_id = await _resolve_link_code(redis, body.link_code)

    await save_oauth_state(
        redis, state,
        provider="vk_id",
        code_verifier=code_verifier,
        device_id=device_id,
        link_user_id=link_user_id,
    )

    url = build_authorize_url(state, redirect_uri, code_challenge)
    return OAuthInitResponse(authorize_url=url)


@router.get("/auth/vk-id/callback")
async def vk_id_oauth_callback(
    code: str = "",
    state: str = "",
    device_id: str = "",
    payload: str = "",
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    import json as _json
    from src.channels.vk_id_auth import exchange_code, get_user_info
    from src.services.oauth_state import pop_oauth_state
    from fastapi.responses import RedirectResponse

    if payload:
        try:
            pl = _json.loads(payload)
            code = code or pl.get("code", "")
            state = state or pl.get("state", "")
            device_id = device_id or pl.get("device_id", "")
        except (ValueError, TypeError):
            pass

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    stored = await pop_oauth_state(redis, state)
    if stored is None or stored.get("provider") != "vk_id":
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    code_verifier = stored.get("code_verifier", "")
    vk_device_id = device_id or stored.get("device_id", "")
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/vk-id/callback"

    if not device_id:
        logger.warning("VK ID callback: device_id not returned by VK, using stored fallback")

    access_token = await exchange_code(
        code, redirect_uri, code_verifier, vk_device_id, state,
    )
    if not access_token:
        raise HTTPException(status_code=401, detail="VK ID token exchange failed")

    vk_user = await get_user_info(access_token)
    if vk_user is None or not vk_user.user_id:
        raise HTTPException(status_code=401, detail="Failed to fetch VK ID user info")

    display = " ".join(
        n for n in (vk_user.first_name, vk_user.last_name) if n
    ) or None

    link_user_id = stored.get("link_user_id")
    link_to = None
    if link_user_id:
        import uuid as _uuid
        link_to = await db.get(User, _uuid.UUID(link_user_id))

    user = await _find_or_create_by_identity(
        db, "vk_id", vk_user.user_id,
        display_name=display,
        profile_data={
            "first_name": vk_user.first_name,
            "last_name": vk_user.last_name,
            "email": vk_user.email,
        },
        link_to_user=link_to,
    )
    token = await create_session(redis, user.id)

    web_base = settings.web_base_url or settings.api_base_url
    return RedirectResponse(
        url=f"{web_base}/auth/callback?token={token}&provider=vk_id&user_id={user.id}",
    )


# ------------------------------------------------------------------
# Phone auth (OTP)
# ------------------------------------------------------------------

_OTP_PREFIX = "ratemeai:phone_otp:"
_OTP_TTL = 300
_OTP_LENGTH = 4


@router.post("/auth/phone/send-code", status_code=200)
async def phone_send_code(
    body: PhoneOTPRequestBody,
    redis: Redis = Depends(get_redis),
):
    import random

    phone = body.phone.strip().lstrip("+")
    code = "".join(str(random.randint(0, 9)) for _ in range(_OTP_LENGTH))

    await redis.set(f"{_OTP_PREFIX}{phone}", code, ex=_OTP_TTL)

    logger.info("OTP sent for phone +%s***%s", phone[:3], phone[-2:])

    return {"sent": True, "phone": phone, "ttl": _OTP_TTL}


@router.post("/auth/phone/verify", response_model=ChannelAuthResponse)
async def phone_verify(
    body: PhoneOTPVerifyBody,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    phone = body.phone.strip().lstrip("+")
    key = f"{_OTP_PREFIX}{phone}"
    stored_code = await redis.get(key)

    if stored_code is None:
        raise HTTPException(status_code=400, detail="Code expired or not requested")
    if (stored_code.decode() if isinstance(stored_code, bytes) else stored_code) != body.code:
        raise HTTPException(status_code=401, detail="Invalid code")

    await redis.delete(key)

    link_to = None
    link_user_id = await _resolve_link_code(redis, body.link_code)
    if link_user_id:
        import uuid as _uuid
        link_to = await db.get(User, _uuid.UUID(link_user_id))

    user = await _find_or_create_by_identity(
        db, "phone", phone,
        profile_data={"phone": f"+{phone}"},
        link_to_user=link_to,
    )
    return await _auth_response(user, db, redis)


# ------------------------------------------------------------------
# Identity listing
# ------------------------------------------------------------------

@router.get("/users/me/identities", response_model=UserIdentitiesResponse)
async def get_my_identities(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
):
    return UserIdentitiesResponse(
        user_id=user.id,
        identities=await _identities_list(db, user.id),
    )


# ------------------------------------------------------------------
# Universal Link Token (cross-platform account linking)
# ------------------------------------------------------------------

def _generate_link_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(_LINK_TOKEN_LENGTH))


@router.post("/auth/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    user: User = Depends(get_auth_user),
    redis: Redis = Depends(get_redis),
):
    """Generate a 6-character code that another platform can use to link to this account."""
    code = _generate_link_code()
    key = f"{_LINK_TOKEN_PREFIX}{code}"
    await redis.set(key, str(user.id), ex=_LINK_TOKEN_TTL)
    web_base = settings.web_base_url or settings.api_base_url
    return LinkTokenResponse(
        code=code,
        ttl=_LINK_TOKEN_TTL,
        link_url=f"{web_base}/link?code={code}",
    )


@router.post("/auth/claim-link", response_model=ClaimLinkResponse)
async def claim_link(
    body: ClaimLinkRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Use a link code to attach the caller's provider identity to the code owner's account."""
    key = f"{_LINK_TOKEN_PREFIX}{body.code.upper().strip()}"
    raw = await redis.get(key)
    if raw is None:
        raise HTTPException(status_code=400, detail="Invalid or expired link code")

    await redis.delete(key)

    import uuid as _uuid
    target_user_id = _uuid.UUID(raw)
    target_user = await db.get(User, target_user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Link code owner not found")

    user = await _find_or_create_by_identity(
        db, body.provider, body.external_id,
        profile_data=body.profile_data,
        link_to_user=target_user,
    )

    return await _claim_link_response(user, db, redis)


async def _claim_link_response(user: User, db: AsyncSession, redis: Redis) -> ClaimLinkResponse:
    token = await create_session(redis, user.id)
    usage = await _usage_for(user, db)
    identities = await _identities_list(db, user.id)
    return ClaimLinkResponse(
        session_token=token,
        user_id=user.id,
        usage=usage,
        identities=identities,
    )
