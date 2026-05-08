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
    return_path: str | None = None,
) -> None:
    """Persist OAuth state in Redis.

    ``return_path`` is the SPA path to navigate to after a successful
    callback (e.g. ``/visa/schengen``). Storing it server-side instead
    of in browser ``sessionStorage`` lets the round-trip survive when
    the OAuth provider sends the user to a different origin than the
    one they started on (vercel.app vs ailookstudio.ru) — the previous
    ``sessionStorage`` approach silently fell back to ``/`` whenever
    that happened.
    """
    payload = json.dumps(
        {
            "provider": provider,
            "code_verifier": code_verifier,
            "device_id": device_id,
            "link_user_id": link_user_id,
            "return_path": return_path,
        }
    )
    await redis.set(f"{_PREFIX}{state}", payload, ex=_TTL)


async def pop_oauth_state(redis: Redis, state: str) -> dict | None:
    key = f"{_PREFIX}{state}"
    raw = await redis.get(key)
    if raw is None:
        return None
    await redis.delete(key)
    return json.loads(raw)
