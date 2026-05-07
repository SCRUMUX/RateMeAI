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

1.55.4 — removed ``lru_cache`` from the parsers. The cache pinned the
first parsed value for the lifetime of the process, which made it
impossible to detect mid-deploy mistakes (e.g. ``.env.ru`` written
AFTER the FastAPI app started would never be picked up — and there
would be no way to tell from the outside). Splitting a 2-element list
on every request is essentially free, and dropping the cache
unblocked the new ``GET /admin/_whoami`` diagnostic endpoint that
needs to read whichever value is currently configured.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_auth_user, get_db
from src.config import settings
from src.models.db import User, UserIdentity
from src.services.admin_lookup import collect_identity_emails


def _parse_admin_ids(raw: str) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


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


def _user_id_in_admin_ids(user: User, allowed: frozenset[str]) -> bool:
    if not allowed:
        return False
    return str(user.id) in allowed


async def _user_admin_email_match(
    db: AsyncSession, user: User, allowed: frozenset[str]
) -> tuple[bool, list[str]]:
    """Return ``(matched, all_user_emails)``.

    Returning the full email list (not just a bool) lets the
    diagnostic ``_whoami`` endpoint report what emails the user has
    on file vs. what's whitelisted, without ever leaking the
    whitelist itself.
    """
    rows = await db.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )
    identities = list(rows.scalars().all())
    emails = collect_identity_emails(identities)
    if not allowed:
        return False, emails
    matched = any(e.strip().lower() in allowed for e in emails)
    return matched, emails


async def _user_has_admin_email(
    db: AsyncSession, user: User, allowed: frozenset[str]
) -> bool:
    if not allowed:
        return False
    matched, _ = await _user_admin_email_match(db, user, allowed)
    return matched


async def require_admin(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: 403 unless the user passes either whitelist."""
    if _user_id_in_admin_ids(user, get_admin_ids()):
        return user
    if await _user_has_admin_email(db, user, get_admin_emails()):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")


# ---------------------------------------------------------------------------
# /admin/_whoami — non-secret diagnostic for "why am I 403?"
# ---------------------------------------------------------------------------
#
# Authenticated but NOT gated by ``require_admin``. Returns enough
# information to diagnose a 403 without leaking the whitelist itself:
#
#   * ``is_admin``: did this user pass the gate?
#   * ``matched_via``: ``"user_id"`` | ``"email"`` | ``null``
#   * ``identity_emails``: emails the user has on file (already
#     visible to the user themselves elsewhere — no PII escape).
#   * ``whitelist_size``: just a count, never the actual values.
#   * ``deployment_mode`` / ``market_id``: helps the operator confirm
#     they hit the region they think they hit.
#
# This endpoint is the missing observability layer: previously a 403
# from any admin route gave zero hints whether the env var was empty,
# the wrong email, or the wrong region. Now the SPA can call it from
# the AdminLayout to render an actionable banner.
router = APIRouter()


@router.get("/_whoami")
async def admin_whoami(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Diagnostic ping. Auth required, admin gate NOT required."""
    user_ids = get_admin_ids()
    emails = get_admin_emails()
    matched_id = _user_id_in_admin_ids(user, user_ids)
    matched_email, identity_emails = await _user_admin_email_match(
        db, user, emails
    )
    matched_via: str | None
    if matched_id:
        matched_via = "user_id"
    elif matched_email:
        matched_via = "email"
    else:
        matched_via = None

    sha = (settings.deploy_git_sha or "").strip()
    return {
        "user_id": str(user.id),
        "is_admin": bool(matched_id or matched_email),
        "matched_via": matched_via,
        "identity_emails": identity_emails,
        "whitelist_size": {
            "user_ids": len(user_ids),
            "emails": len(emails),
        },
        "deployment_mode": settings.deployment_mode,
        "market_id": settings.resolved_market_id,
        "git": sha[:12] if sha else None,
    }
