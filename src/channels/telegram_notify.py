"""Telegram push notifications (extracted from payments for reuse)."""

from __future__ import annotations

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


async def send_telegram_message(telegram_id: int, text: str) -> bool:
    token = settings.telegram_bot_token
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Telegram notify failed: %s %s", resp.status_code, resp.text[:200]
                )
                return False
            return True
    except Exception:
        logger.exception("Failed to send Telegram message to %s", telegram_id)
        return False
