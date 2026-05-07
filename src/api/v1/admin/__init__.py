"""Admin-only HTTP surface mounted under ``/api/v1/admin``.

All routes in this package (except ``/admin/_whoami``) require the
caller to be both authenticated (``Authorization: Bearer <session-token>``
or ``X-API-Key``) AND listed in either ``ADMIN_USER_IDS`` (UUID) or
``ADMIN_EMAILS`` (email whitelist). See :mod:`src.api.v1.admin.auth`
for the gate. ``/admin/_whoami`` is intentionally NOT admin-gated —
it's a diagnostic surface that tells the caller WHY they would be
rejected by the gate (introduced in 1.55.4 to replace the silent 403
that was breaking the operator UX).
"""

from src.api.v1.admin.auth import router as admin_diag_router
from src.api.v1.admin.styles import router as styles_router
from src.api.v1.admin.landing import router as admin_landing_router
from src.api.v1.admin.users import router as admin_users_router

__all__ = [
    "admin_diag_router",
    "styles_router",
    "admin_landing_router",
    "admin_users_router",
]
