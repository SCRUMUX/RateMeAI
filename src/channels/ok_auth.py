"""Odnoklassniki launch-parameter signature verification."""

from __future__ import annotations

import hashlib

from src.config import settings


def verify_ok_auth_sig(logged_user_id: str, session_key: str, auth_sig: str) -> bool:
    """Verify auth_sig = md5(logged_user_id + session_key + application_secret_key)."""
    secret = settings.ok_app_secret_key
    if not secret:
        return False
    expected = hashlib.md5(
        f"{logged_user_id}{session_key}{secret}".encode()
    ).hexdigest()
    return expected.lower() == auth_sig.lower()
