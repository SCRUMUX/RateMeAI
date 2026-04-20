"""Bot utilities for working with Telegram-uploaded photos."""
from __future__ import annotations

import io
import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


async def download_photo_bytes(bot: Bot, file_id: str) -> bytes:
    """Download a Telegram file by id and return raw bytes.

    Small wrapper around bot.get_file/download_file that is used in several
    places (pre-flight gate, generation, etc.).
    """
    file_obj = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(file_obj.file_path, buf)
    buf.seek(0)
    return buf.read()
