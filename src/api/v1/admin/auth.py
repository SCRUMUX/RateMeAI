"""Admin-only access gate for ``/api/v1/admin/*``.

Whitelist-based: the env var ``ADMIN_USER_IDS`` (comma-separated user
IDs in the same string form as ``User.id`` in the DB) defines who can
call any admin endpoint. Anyone authenticated but not listed gets a
plain 403; unauthenticated callers get a 401 from the upstream
``get_auth_user`` dependency. Empty whitelist = endpoint locked for
everyone (the safe production default for fresh deploys).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException

from src.api.deps import get_auth_user
from src.config import settings
from src.models.db import User


@lru_cache(maxsize=1)
def _parse_admin_ids(raw: str) -> frozenset[str]:
    """Split the comma-separated env var into a normalized set.

    Cached because it's read on every admin request and the env var
    only changes on process restart. Whitespace around each id is
    tolerated so operators can paste values like ``"a, b, c"`` from
    Railway's UI without surprises.
    """
    if not raw:
        return frozenset()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def get_admin_ids() -> frozenset[str]:
    """Public helper for tests/diagnostics."""
    return _parse_admin_ids(settings.admin_user_ids or "")


async def require_admin(user: User = Depends(get_auth_user)) -> User:
    """FastAPI dependency: 403 unless ``user.id`` is whitelisted.

    Use as ``Depends(require_admin)`` on every admin route. Stacked on
    top of ``get_auth_user`` so any 401 / consent / rate-limit wiring
    elsewhere keeps working — admins are still real users.
    """
    admin_ids = get_admin_ids()
    if str(user.id) not in admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
