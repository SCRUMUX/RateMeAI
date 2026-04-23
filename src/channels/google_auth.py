"""Google OAuth 2.0 Authorization Code flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USER_INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@dataclass
class GoogleUser:
    id: str
    email: str | None
    name: str | None
    picture: str | None


def build_authorize_url(state: str, redirect_uri: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return str(httpx.URL(AUTHORIZE_URL, params=params))


async def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange authorization code for access_token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.error("Google token exchange failed: %s %s", resp.status_code, resp.text)
        return ""
    return resp.json().get("access_token", "")


async def get_user_info(access_token: str) -> GoogleUser | None:
    """Fetch user profile from Google userinfo endpoint."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        logger.error("Google user info failed: %s %s", resp.status_code, resp.text)
        return None
    data = resp.json()
    sub = data.get("sub", "")
    if not sub:
        return None
    return GoogleUser(
        id=sub,
        email=data.get("email"),
        name=data.get("name"),
        picture=data.get("picture"),
    )
