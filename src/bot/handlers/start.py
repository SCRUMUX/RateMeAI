from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
import httpx

from src.bot.keyboards import back_keyboard, upgrade_keyboard

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = """👋 Привет! Я *RateMe AI* — твой AI-стилист.

Покажу, как тебя воспринимают, и помогу усилить образ для разных жизненных ситуаций.

Что я умею:
⭐ *Анализ восприятия* — как тебя видят окружающие
💕 *Стиль для знакомств* — образы для дейтинга
💼 *Карьерный стиль* — профессиональный образ
📸 *Стиль для соцсетей* — образы для Instagram и соцсетей

*Отправь мне фото* и выбери направление!

💰 /balance — проверить баланс образов"""

REFERRAL_TEXT = """🎁 Тебя пригласил друг! Отправь фото и узнай, как тебя воспринимают."""


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


@router.message(Command("emoji"))
async def cmd_emoji(message: Message):
    """Access emoji mode via /emoji command."""
    await message.answer(
        "😀 *Эмодзи-пак*\n\nОтправь мне фото, а затем выбери 😀 Эмодзи в меню после результата.",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


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
            text = f"💰 *Твой баланс: {credits} образов*\n\n"
            if credits == 0:
                text += "Открой новые образы и стили!"
                await message.answer(text, parse_mode="Markdown", reply_markup=upgrade_keyboard())
            else:
                text += "Отправь фото для примерки образа!"
                await message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            await message.answer("❌ Не удалось получить баланс.", reply_markup=back_keyboard())
    except Exception:
        logger.exception("Failed to fetch balance for user %s", user_id)
        await message.answer("❌ Ошибка. Попробуй позже.", reply_markup=back_keyboard())


async def _get_balance_line(api_base_url: str, user_id: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/payments/balance",
                headers={"X-Telegram-Id": str(user_id)},
            )
        if resp.status_code == 200:
            credits = resp.json().get("image_credits", 0)
            return f"💰 Баланс: *{credits} образов*"
    except Exception:
        logger.debug("Could not fetch balance for start message, user=%s", user_id)
    return ""
