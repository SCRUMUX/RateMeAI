from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.bot.keyboards import back_keyboard

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = """👋 Привет! Я **RateMe AI** — бот, который анализирует, как тебя воспринимают по фото.

Что я умею:
⭐ **Рейтинг** — честная оценка 0–10 с разбором
💕 **Дейтинг** — анализ для свиданий + рекомендации
💼 **CV** — оценка для профессионального фото
😀 **Эмодзи** — пак стикеров с твоим лицом

**Просто отправь мне фото** и выбери режим!"""

REFERRAL_TEXT = """🎁 Тебя пригласил друг! Отправь фото и узнай свой рейтинг."""


@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split(maxsplit=1)
    referral = None
    if len(args) > 1 and args[1].startswith("ref_"):
        referral = args[1]
        logger.info("Referral start: user=%s ref=%s", message.from_user.id, referral)

    text = REFERRAL_TEXT if referral else WELCOME_TEXT
    await message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())
