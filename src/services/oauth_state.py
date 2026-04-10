"""OAuth state + PKCE code_verifier storage in Redis."""
from __future__ import annotations

import hashlib
import base64
import json
import secrets

from redis.asyncio import Redis

_PREFIX = "ratemeai:oauth_state:"
_TTL = 600  # 10 minutes


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def save_oauth_state(
    redis: Redis,
    state: str,
    *,
    provider: str,
    code_verifier: str | None = None,
    device_id: str | None = None,
    link_user_id: str | None = None,
) -> None:
    payload = json.dumps({
        "provider": provider,
        "code_verifier": code_verifier,
        "device_id": device_id,
        "link_user_id": link_user_id,
    })
    await redis.set(f"{_PREFIX}{state}", payload, ex=_TTL)


async def pop_oauth_state(redis: Redis, state: str) -> dict | None:
    key = f"{_PREFIX}{state}"
    raw = await redis.get(key)
    if raw is None:
        return None
    await redis.delete(key)
    return json.loads(raw)
