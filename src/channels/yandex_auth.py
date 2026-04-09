"""Yandex ID OAuth 2.0 Authorization Code flow."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://oauth.yandex.com/authorize"
TOKEN_URL = "https://oauth.yandex.com/token"
USER_INFO_URL = "https://login.yandex.ru/info"


@dataclass
class YandexUser:
    id: str
    login: str
    display_name: str | None
    default_email: str | None


def build_authorize_url(state: str, redirect_uri: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "force_confirm": "yes",
    }
    return str(httpx.URL(AUTHORIZE_URL, params=params))


async def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange authorization code for access_token. Returns the token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.yandex_client_id,
                "client_secret": settings.yandex_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.error("Yandex token exchange failed: %s %s", resp.status_code, resp.text)
        return ""
    return resp.json().get("access_token", "")


async def get_user_info(access_token: str) -> YandexUser | None:
    """Fetch user profile from Yandex ID API."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            USER_INFO_URL,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        )
    if resp.status_code != 200:
        logger.error("Yandex user info failed: %s %s", resp.status_code, resp.text)
        return None
    data = resp.json()
    return YandexUser(
        id=str(data.get("id", "")),
        login=data.get("login", ""),
        display_name=data.get("display_name") or data.get("login"),
        default_email=data.get("default_email"),
    )
