"""Shared user lookup helpers used by ``/api/v1/admin`` and the
internal ``/api/v1/internal/admin`` surfaces.

The previous home of these helpers was ``src/api/v1/internal.py``,
where they only served the ``X-Internal-Key`` ``grant-credits``
endpoint. The session-admin Users tab needs the same primitives —
in particular ``format_user_summary`` for transaction/audit log
rows that should look identical regardless of which surface
created them.

Pure data shaping + one search helper. No HTTP concerns, no
auth — that lives in the route handlers.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import User, UserIdentity


def format_user_summary(
    user: User, identity: UserIdentity | None
) -> dict[str, Any]:
    """Backward-compatible projection used by ``admin/grant-credits``.

    Kept verbatim so existing GitHub Actions logs and the admin
    bot don't suddenly start parsing a different shape.
    """
    data: dict[str, Any] = (identity.profile_data or {}) if identity else {}
    return {
        "user_id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "credits_before": user.image_credits,
        "provider": identity.provider if identity else None,
        "external_id": identity.external_id if identity else None,
        "profile_username": data.get("username"),
        "profile_first_name": data.get("first_name"),
        "profile_last_name": data.get("last_name"),
        "profile_email": data.get("email"),
    }


def collect_identity_emails(identities: Iterable[UserIdentity]) -> list[str]:
    """Pluck distinct emails from any identity's ``profile_data``.

    A single user may have several identities (telegram + google,
    for example). Lower-case + dedup so the UI can show "all
    emails on file" without surprise duplicates.
    """
    seen: set[str] = set()
    out: list[str] = []
    for ident in identities:
        data = ident.profile_data or {}
        email = data.get("email")
        if not isinstance(email, str):
            continue
        norm = email.strip().lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(email.strip())
    return out


async def search_users_by_query(
    db: AsyncSession,
    q: str,
    *,
    limit: int = 50,
) -> list[User]:
    """Substring search across ``username`` / ``telegram_id`` /
    ``user_identities.profile_data->>'email'``.

    Returns distinct users ordered by ``created_at desc``. Empty
    ``q`` returns the most recent users — that's the natural
    "browse" shape for the admin Users tab.
    """
    needle = (q or "").strip()
    base = (
        select(User)
        .order_by(User.created_at.desc())
        .limit(limit)
    )

    if not needle:
        return list((await db.execute(base)).scalars().all())

    needle_lower = needle.lower()
    like_pat = f"%{needle_lower}%"
    tg_int: int | None = None
    try:
        tg_int = int(needle)
    except ValueError:
        tg_int = None

    user_filters = [
        User.username.ilike(like_pat),
    ]
    if tg_int is not None:
        user_filters.append(User.telegram_id == tg_int)

    matched_ids: set = set()
    direct_q = (
        select(User)
        .where(or_(*user_filters))
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    for u in (await db.execute(direct_q)).scalars().all():
        matched_ids.add(u.id)

    # Email / nickname-in-profile-data search — JSON cast varies by
    # backend, so we filter in Python after pulling the candidate
    # window. The window is bounded by ``limit`` * a small fanout,
    # so this never returns more than a few hundred rows even on
    # large user bases.
    ident_q = (
        select(UserIdentity)
        .order_by(UserIdentity.created_at.desc())
        .limit(limit * 4)
    )
    extra_user_ids: list = []
    for ident in (await db.execute(ident_q)).scalars().all():
        if ident.user_id in matched_ids:
            continue
        data = ident.profile_data or {}
        haystacks: list[str] = []
        for key in ("email", "username", "first_name", "last_name"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                haystacks.append(val.strip().lower())
        if any(needle_lower in h for h in haystacks):
            if ident.user_id not in matched_ids:
                matched_ids.add(ident.user_id)
                extra_user_ids.append(ident.user_id)

    if not matched_ids:
        return []

    final_q = (
        select(User)
        .where(User.id.in_(list(matched_ids)))
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(final_q)).scalars().all())
