"""Admin-only HTTP surface mounted under ``/api/v1/admin``.

All routes in this package require the caller to be both authenticated
(``Authorization: Bearer <session-token>`` or ``X-API-Key``) AND listed
in the ``ADMIN_USER_IDS`` env var. See :mod:`src.api.v1.admin.auth` for
the gate.
"""

from src.api.v1.admin.styles import router as styles_router

__all__ = ["styles_router"]
