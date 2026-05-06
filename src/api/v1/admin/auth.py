"""Admin-only access gate for ``/api/v1/admin/*``.

Whitelist-based with two independent sources:

1. ``ADMIN_USER_IDS`` — comma-separated ``User.id`` UUIDs (legacy path,
   keeps existing operators working).
2. ``ADMIN_EMAILS`` — comma-separated email addresses. The gate looks
   them up in ``user_identities.profile_data->>'email'`` (matching
   any provider that stored an email — google / yandex / vk_id /
   apple). Easier to onboard new admins: you drop the email into the
   env var and the next OAuth login is authorised, no DB lookup
   required.

Both env vars are optional. Empty whitelists = endpoint locked for
everyone (the safe production default for fresh deploys).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_auth_user, get_db
from src.config import settings
from src.models.db import User, UserIdentity


@lru_cache(maxsize=1)
def _parse_admin_ids(raw: str) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


@lru_cache(maxsize=1)
def _parse_admin_emails(raw: str) -> frozenset[str]:
    """Lower-cased email whitelist for case-insensitive matching."""
    if not raw:
        return frozenset()
    return frozenset(
        p.strip().lower() for p in raw.split(",") if p.strip()
    )


def get_admin_ids() -> frozenset[str]:
    """Public helper for tests/diagnostics."""
    return _parse_admin_ids(settings.admin_user_ids or "")


def get_admin_emails() -> frozenset[str]:
    """Public helper for tests/diagnostics."""
    return _parse_admin_emails(settings.admin_emails or "")


async def _user_has_admin_email(
    db: AsyncSession, user: User, allowed: frozenset[str]
) -> bool:
    if not allowed:
        return False
    rows = await db.execute(
        select(UserIdentity.profile_data).where(UserIdentity.user_id == user.id)
    )
    for (profile,) in rows.all():
        if not profile or not isinstance(profile, dict):
            continue
        email = profile.get("email")
        if isinstance(email, str) and email.strip().lower() in allowed:
            return True
    return False


async def require_admin(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: 403 unless the user passes either whitelist."""
    if str(user.id) in get_admin_ids():
        return user
    if await _user_has_admin_email(db, user, get_admin_emails()):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")
