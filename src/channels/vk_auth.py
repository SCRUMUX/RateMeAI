"""VK Mini Apps launch-parameter verification."""
from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import parse_qs, urlencode

from src.config import settings


def verify_vk_launch_params(query_string: str) -> str | None:
    """Verify VK Mini Apps launch params signature.

    Returns the vk_user_id if signature is valid, None otherwise.
    Expects the raw query string that VK passes to the mini app iframe.
    """
    secret = settings.vk_app_secret
    if not secret:
        return None

    params = parse_qs(query_string, keep_blank_values=True)

    sign_value = params.pop("sign", [None])[0]
    if not sign_value:
        return None

    # VK-specific: only params starting with "vk_" are signed
    vk_params = {k: v[0] for k, v in sorted(params.items()) if k.startswith("vk_")}
    param_string = urlencode(vk_params)

    expected = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), param_string.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")

    if not hmac.compare_digest(expected, sign_value):
        return None

    return vk_params.get("vk_user_id")
