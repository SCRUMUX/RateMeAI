from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
import httpx

from src.bot.keyboards import back_keyboard, upgrade_keyboard

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = """👋 Привет! Я **RateMe AI** — бот, который анализирует, как тебя воспринимают по фото.

Что я умею:
⭐ **Рейтинг** — честная оценка 0–10 с разбором
💕 **Дейтинг** — анализ для свиданий + рекомендации
💼 **CV** — оценка для профессионального фото
😀 **Эмодзи** — пак стикеров с твоим лицом

**Просто отправь мне фото** и выбери режим!

💰 /balance — проверить баланс генераций"""

REFERRAL_TEXT = """🎁 Тебя пригласил друг! Отправь фото и узнай свой рейтинг."""


@router.message(CommandStart())
async def cmd_start(message: Message, api_base_url: str):
    args = message.text.split(maxsplit=1)
    referral = None
    if len(args) > 1 and args[1].startswith("ref_"):
        referral = args[1]
        logger.info("Referral start: user=%s ref=%s", message.from_user.id, referral)

    text = REFERRAL_TEXT if referral else WELCOME_TEXT

    balance_line = await _get_balance_line(api_base_url, message.from_user.id)
    if balance_line:
        text += f"\n\n{balance_line}"

    await message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())


@router.message(Command("balance"))
async def cmd_balance(message: Message, api_base_url: str):
    user_id = message.from_user.id
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/payments/balance",
                headers={"X-Telegram-Id": str(user_id)},
            )
        if resp.status_code == 200:
            credits = resp.json().get("image_credits", 0)
            text = f"💰 *Твой баланс: {credits} генераций*\n\n"
            if credits == 0:
                text += "Купи пакет, чтобы генерировать фото!"
                await message.answer(text, parse_mode="Markdown", reply_markup=upgrade_keyboard())
            else:
                text += "Отправь фото для генерации!"
                await message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            await message.answer("❌ Не удалось получить баланс.")
    except Exception:
        logger.exception("Failed to fetch balance for user %s", user_id)
        await message.answer("❌ Ошибка. Попробуй позже.")


async def _get_balance_line(api_base_url: str, user_id: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/payments/balance",
                headers={"X-Telegram-Id": str(user_id)},
            )
        if resp.status_code == 200:
            credits = resp.json().get("image_credits", 0)
            return f"💰 Баланс: *{credits} генераций*"
    except Exception:
        logger.debug("Could not fetch balance for start message, user=%s", user_id)
    return ""
