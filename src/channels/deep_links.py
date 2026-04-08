"""Platform-aware deep link and share URL generation."""
from __future__ import annotations

from src.config import settings

PROVIDER_TELEGRAM = "telegram"
PROVIDER_OK = "ok"
PROVIDER_VK = "vk"
PROVIDER_WEB = "web"
PROVIDER_WHATSAPP = "whatsapp"


def build_deep_link(user_id: str, channel: str = PROVIDER_TELEGRAM) -> str:
    if channel == PROVIDER_OK and settings.ok_app_id:
        return f"https://ok.ru/game/{settings.ok_app_id}?ref={user_id}"

    if channel == PROVIDER_VK and settings.vk_app_id:
        return f"https://vk.com/app{settings.vk_app_id}#ref={user_id}"

    if channel == PROVIDER_WEB and settings.web_base_url:
        base = settings.web_base_url.rstrip("/")
        return f"{base}/?ref={user_id}"

    uname = settings.telegram_bot_username.lstrip("@")
    return f"https://t.me/{uname}?start=ref_{user_id}"


def build_share_caption(result: dict, channel: str = PROVIDER_TELEGRAM) -> str:
    """Build a human-readable share caption with a platform-appropriate CTA."""
    link_label = _cta_label(channel)

    score = result.get("score")
    if score is not None:
        return f"Мой рейтинг: {score}/10 — {link_label}"

    dating = result.get("dating_score")
    if dating is not None:
        return f"Стиль для знакомств: {dating}/10 — {link_label}"

    social = result.get("social_score")
    if social is not None:
        return f"Стиль для соцсетей: {social}/10 — {link_label}"

    hire = result.get("hireability")
    if hire is not None:
        return f"Карьерный стиль: {hire}/10 — {link_label}"

    return f"Смотри мой результат — {link_label}"


def _cta_label(channel: str) -> str:
    if channel == PROVIDER_TELEGRAM:
        uname = settings.telegram_bot_username.lstrip("@")
        return f"узнай свой → @{uname}"
    if channel == PROVIDER_OK:
        return "попробуй в ОК!"
    if channel == PROVIDER_VK:
        return "попробуй в ВК!"
    if channel == PROVIDER_WEB and settings.web_base_url:
        return f"попробуй → {settings.web_base_url}"
    return "попробуй!"
