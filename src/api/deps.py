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
    return {p.strip().lstrip("@").lower() for p in raw.split(",") if p.strip()}


def _user_exempt_from_rate_limit(user: User) -> bool:
    if not user.username:
        return False
    uname = user.username.strip().lstrip("@").lower()
    return uname in _rate_limit_exempt_usernames()


def ensure_user_not_blocked(user: User) -> None:
    """Raise HTTP 403 ``account_blocked`` if the user is soft-blocked.

    Called from ``get_auth_user`` (every authenticated request) AND
    from auth handlers right before issuing a session token, so a
    blocked user can't grab a fresh token only to get 403 on the
    next request. The frontend listens for the ``account_blocked``
    code and shows a full-screen overlay.
    """
    if user.blocked_at is not None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "account_blocked",
                "reason": user.blocked_reason or "",
            },
        )


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.db_sessionmaker() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_auth_user(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    # 1) Bearer session token (web / bot / mini apps)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            from src.services.sessions import resolve_session

            redis = request.app.state.redis
            user_id = await resolve_session(redis, token)
            if user_id is None:
                raise HTTPException(
                    status_code=401, detail="Invalid or expired session token"
                )
            user = await db.get(User, user_id)
            if user is None:
                raise HTTPException(
                    status_code=401, detail="User not found for session"
                )
            ensure_user_not_blocked(user)
            return user

    # 2) API key (B2B)
    if x_api_key:
        h = hash_api_key(x_api_key.strip(), _pepper())
        r = await db.execute(
            select(ApiClient).where(
                ApiClient.key_hash == h, ApiClient.is_active.is_(True)
            )
        )
        client = r.scalar_one_or_none()
        if client is None:
            raise HTTPException(status_code=401, detail="Invalid or inactive API key")
        user = await db.get(User, client.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        ensure_user_not_blocked(user)
        return user

    raise HTTPException(
        status_code=401,
        detail="Provide Authorization: Bearer <token> or X-API-Key header",
    )


async def get_current_user(user: User = Depends(get_auth_user)) -> User:
    return user


async def get_optional_auth_user(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Soft variant of :func:`get_auth_user` for endpoints that work
    for both anonymous and authenticated callers.

    Returns the resolved :class:`User` if the request carries a valid
    Bearer token or X-API-Key, otherwise ``None``. Never raises 401 —
    a missing / invalid / expired credential simply yields ``None``.
    Blocked users still raise 403 via :func:`ensure_user_not_blocked`
    (a blocked user MUST NOT silently degrade to anonymous on a
    "public" endpoint — that would let them bypass the block).

    v1.76 — added so the web catalog endpoint can use the user's
    UUID as a deterministic shuffle seed when available and fall
    back to a per-IP / per-day seed for anonymous callers, giving
    every visitor a stable but distinct catalog ordering.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            from src.services.sessions import resolve_session

            try:
                redis = request.app.state.redis
                user_id = await resolve_session(redis, token)
            except Exception:
                user_id = None
            if user_id is not None:
                user = await db.get(User, user_id)
                if user is not None:
                    ensure_user_not_blocked(user)
                    return user

    if x_api_key:
        try:
            h = hash_api_key(x_api_key.strip(), _pepper())
            r = await db.execute(
                select(ApiClient).where(
                    ApiClient.key_hash == h, ApiClient.is_active.is_(True)
                )
            )
            client = r.scalar_one_or_none()
        except Exception:
            client = None
        if client is not None:
            user = await db.get(User, client.user_id)
            if user is not None:
                ensure_user_not_blocked(user)
                return user

    return None


def _parse_bool_header(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


async def require_consents(
    request: Request,
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
    x_consent_data_processing: str | None = Header(
        None, alias="X-Consent-Data-Processing"
    ),
    x_consent_ai_transfer: str | None = Header(None, alias="X-Consent-AI-Transfer"),
    x_consent_age_16: str | None = Header(None, alias="X-Consent-Age-16"),
) -> User:
    """Enforce both mandatory consents.

    B2B API clients can opt-in inline via ``X-Consent-*`` headers (auto-grant
    for the request, persisted once). Web/bot users must have granted consents
    via ``POST /users/me/consents`` beforehand.

    Returns HTTP 451 with ``{code, missing}`` detail when any consent is absent.
    """
    from src.services.consent import (
        REQUIRED_CONSENT_KINDS,
        CONSENT_DATA_PROCESSING,
        CONSENT_AI_TRANSFER,
        CONSENT_AGE_CONFIRMED_16,
        get_active_consents,
        grant_consent,
        hash_marker,
        missing_required,
    )

    redis = request.app.state.redis
    active = await get_active_consents(db, redis, user.id)
    missing = missing_required(active)

    if missing:
        header_grants: list[str] = []
        if CONSENT_DATA_PROCESSING in missing and _parse_bool_header(
            x_consent_data_processing
        ):
            header_grants.append(CONSENT_DATA_PROCESSING)
        if CONSENT_AI_TRANSFER in missing and _parse_bool_header(x_consent_ai_transfer):
            header_grants.append(CONSENT_AI_TRANSFER)
        if CONSENT_AGE_CONFIRMED_16 in missing and _parse_bool_header(x_consent_age_16):
            header_grants.append(CONSENT_AGE_CONFIRMED_16)
        if header_grants:
            client_ip = request.client.host if request.client else None
            active = await grant_consent(
                db,
                redis,
                user.id,
                header_grants,
                source="api_header",
                ip_hash=hash_marker(client_ip),
                user_agent_hash=hash_marker(request.headers.get("user-agent")),
            )
            missing = missing_required(active)

    if missing:
        raise HTTPException(
            status_code=451,
            detail={
                "code": "consent_required",
                "missing": missing,
                "required": list(REQUIRED_CONSENT_KINDS),
            },
        )
    user._consents_snapshot = active
    return user


async def _reserve_credit_for(user: User, db: AsyncSession) -> User:
    from sqlalchemy import select as sa_select
    from src.models.db import CreditTransaction

    result = await db.execute(
        sa_select(User).where(User.id == user.id).with_for_update()
    )
    fresh_user = result.scalar_one()
    if fresh_user.image_credits <= 0:
        raise HTTPException(
            status_code=402,
            detail="no_credits",
            headers={"X-Credits-Remaining": "0"},
        )
    fresh_user.image_credits -= 1
    db.add(
        CreditTransaction(
            user_id=fresh_user.id,
            amount=-1,
            balance_after=fresh_user.image_credits,
            tx_type="reservation",
        )
    )
    fresh_user._credits_remaining = fresh_user.image_credits
    fresh_user._credit_reserved = True
    fresh_user._consents_snapshot = getattr(user, "_consents_snapshot", None)
    return fresh_user


async def reserve_additional_credit(
    user: User,
    db: AsyncSession,
    *,
    amount: int = 1,
) -> User:
    """Reserve an additional credit on top of the initial reservation.

    v1.72 — used by the premium-tier path on ``POST /analyze`` to
    reserve a second credit (premium = 2 credits total). Atomic
    against concurrent reservations via ``SELECT … FOR UPDATE``.

    Raises ``HTTPException(402)`` when the user does not have
    ``amount`` extra credits available; the handler is expected to
    refund the previously-reserved credit on 402 so the user is
    not left with a half-charged premium request.
    """
    if amount <= 0:
        return user

    from sqlalchemy import select as sa_select
    from src.models.db import CreditTransaction

    result = await db.execute(
        sa_select(User).where(User.id == user.id).with_for_update()
    )
    fresh_user = result.scalar_one()
    if fresh_user.image_credits < amount:
        raise HTTPException(
            status_code=402,
            detail="no_credits",
            headers={"X-Credits-Remaining": str(fresh_user.image_credits)},
        )
    fresh_user.image_credits -= amount
    db.add(
        CreditTransaction(
            user_id=fresh_user.id,
            amount=-amount,
            balance_after=fresh_user.image_credits,
            tx_type="reservation",
        )
    )
    fresh_user._credits_remaining = fresh_user.image_credits
    fresh_user._consents_snapshot = getattr(user, "_consents_snapshot", None)
    return fresh_user


async def refund_credit(
    user: User,
    db: AsyncSession,
    *,
    amount: int = 1,
    reason: str = "refund",
) -> User:
    """Atomically refund ``amount`` credits back to the user.

    v1.72 — used by the premium-tier flow on two paths:
      * ``POST /analyze`` handler when the second-credit reservation
        for premium fails with 402 (we have to roll back the first
        reservation so the user is not partially charged).
      * Worker post-generation flow when the premium refiner failed
        (``result_dict["premium_refine_failed"] == True``) — we
        refund 1 of the 2 reserved credits so the user gets the
        standard render they would have received at the lower tier.

    The function is intentionally permissive about ``amount <= 0``
    (no-op) so callers don't have to guard against zero. Atomic via
    ``SELECT … FOR UPDATE``; same transaction semantics as the
    reservation path.
    """
    if amount <= 0:
        return user

    from sqlalchemy import select as sa_select
    from src.models.db import CreditTransaction

    result = await db.execute(
        sa_select(User).where(User.id == user.id).with_for_update()
    )
    fresh_user = result.scalar_one()
    fresh_user.image_credits += amount
    db.add(
        CreditTransaction(
            user_id=fresh_user.id,
            amount=amount,
            balance_after=fresh_user.image_credits,
            tx_type=reason,
        )
    )
    fresh_user._credits_remaining = fresh_user.image_credits
    return fresh_user


async def check_credits(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Reserve one credit atomically using SELECT FOR UPDATE + immediate decrement.

    If the task fails later, the worker/edge handler refunds the credit.
    This prevents concurrent requests from over-committing credits.
    """
    return await _reserve_credit_for(user, db)


async def check_credits_with_consent(
    user: User = Depends(require_consents),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Consent-gated credit reservation.

    Applied to the user-facing ``POST /analyze``.     The caller must have granted
    ``data_processing``, ``ai_transfer`` and ``age_confirmed_16`` consents,
    otherwise a 451 is raised before any credit is touched.
    """
    return await _reserve_credit_for(user, db)


async def check_rate_limit(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Дневной rate-limit.

    ВНИМАНИЕ: на пользовательском /analyze эта проверка больше НЕ применяется —
    генерация лимитируется исключительно балансом кредитов (см. check_credits).
    Зависимость оставлена для будущих B2B API-клиентов (ApiClient.rate_limit_daily),
    у которых квота выражается в «запросах в сутки», а не в кредитах.
    """
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
        select(UsageLog).where(
            UsageLog.user_id == user.id, UsageLog.usage_date == today
        )
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
