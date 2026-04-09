"""VK ID OAuth 2.1 Authorization Code flow with PKCE."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://id.vk.com/authorize"
TOKEN_URL = "https://id.vk.com/oauth2/auth"
USER_INFO_URL = "https://id.vk.com/oauth2/user_info"


@dataclass
class VKIDUser:
    user_id: str
    first_name: str | None
    last_name: str | None
    email: str | None


def build_authorize_url(
    state: str,
    redirect_uri: str,
    code_challenge: str,
    device_id: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.vk_id_app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "email",
        "device_id": device_id,
    }
    return str(httpx.URL(AUTHORIZE_URL, params=params))


async def exchange_code(
    code: str,
    redirect_uri: str,
    code_verifier: str,
    device_id: str,
    state: str,
) -> str:
    """Exchange authorization code for access_token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.vk_id_app_id,
                "code_verifier": code_verifier,
                "device_id": device_id,
                "state": state,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.error("VK ID token exchange failed: %s %s", resp.status_code, resp.text)
        return ""
    data = resp.json()
    return data.get("access_token", "")


async def get_user_info(access_token: str) -> VKIDUser | None:
    """Fetch user profile from VK ID API."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            USER_INFO_URL,
            data={"access_token": access_token, "client_id": settings.vk_id_app_id},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.error("VK ID user info failed: %s %s", resp.status_code, resp.text)
        return None
    data = resp.json().get("user", resp.json())
    return VKIDUser(
        user_id=str(data.get("user_id", "")),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        email=data.get("email"),
    )
