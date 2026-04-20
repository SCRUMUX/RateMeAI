from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
import httpx
from redis.asyncio import Redis

from src.bot.keyboards import back_keyboard, upgrade_keyboard
from src.services.photo_requirements import (
    format_requirements_plaintext,
    short_requirements_block,
)

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = f"""\u2728 *RateMe AI* \u2014 твой персональный AI-стилист.

Теперь мощь и опыт лучших стилистов мира \u2014 в твоём телефоне.
Давай усилим твой образ для разных жизненных ситуаций:

\U0001f495 *Знакомства* \u2014 образы для дейтинга
\U0001f4bc *Карьера* \u2014 профессиональный образ
\U0001f4f8 *Соцсети* \u2014 образы для Instagram и соцсетей

{short_requirements_block()}

*Отправь мне фото* и выбери направление!

\U0001f4b0 /balance \u2014 проверить баланс образов
\U0001f517 /link \u2014 привязать аккаунт на сайте"""

REFERRAL_TEXT = """\U0001f381 Тебя пригласил друг! Отправь фото и я подберу лучший образ для тебя."""


@router.message(CommandStart())
async def cmd_start(message: Message, api_base_url: str, redis: Redis):
    args = message.text.split(maxsplit=1)
    referral = None
    if len(args) > 1 and args[1].startswith("ref_"):
        referral = args[1]
        logger.info("Referral start: user=%s ref=%s", message.from_user.id, referral)

    text = REFERRAL_TEXT if referral else WELCOME_TEXT

    balance_line = await _get_balance_line(api_base_url, message.from_user, redis)
    if balance_line:
        text += f"\n\n{balance_line}"

    await message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())


@router.message(Command("photo_help"))
async def cmd_photo_help(message: Message):
    """Detailed photo requirements and rejection reasons."""
    await message.answer(
        format_requirements_plaintext(),
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


@router.message(Command("emoji"))
async def cmd_emoji(message: Message, redis: Redis):
    """Access emoji mode via /emoji command — sets flag, then user sends photo."""
    user_id = message.from_user.id
    await redis.set(f"ratemeai:emoji_mode:{user_id}", "1", ex=300)
    await message.answer(
        "\U0001f600 *Эмодзи-пак*\n\nОтправь мне фото, и я сделаю из него стикер-аватар!",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


@router.message(Command("rating"))
async def cmd_rating(message: Message, redis: Redis):
    """Hidden rating mode for advanced users."""
    user_id = message.from_user.id
    await redis.set(f"ratemeai:rating_mode:{user_id}", "1", ex=300)
    await message.answer(
        "\u2b50 *Рейтинг*\n\nОтправь мне фото, чтобы узнать свой рейтинг восприятия.",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


@router.message(Command("balance"))
async def cmd_balance(message: Message, api_base_url: str, redis: Redis):
    from src.bot.handlers.mode_select import _get_api_headers, _refresh_api_headers

    user_id = message.from_user.id
    balance_api = api_base_url
    headers = await _get_api_headers(redis, user_id, balance_api, message.from_user)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{balance_api}/api/v1/payments/balance",
                headers=headers,
            )

        if resp.status_code == 401:
            headers = await _refresh_api_headers(redis, user_id, balance_api, message.from_user)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{balance_api}/api/v1/payments/balance",
                    headers=headers,
                )

        if resp.status_code == 200:
            credits = resp.json().get("image_credits", 0)
            text = f"\U0001f4b0 *Твой баланс: {credits} образов*\n\n"
            if credits == 0:
                text += "Открой новые образы и стили!"
                await message.answer(text, parse_mode="Markdown", reply_markup=upgrade_keyboard())
            else:
                text += "Отправь фото для улучшения образа!"
                await message.answer(text, parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            logger.warning("Balance request failed for user %s: status=%s body=%s", user_id, resp.status_code, resp.text[:300])
            await message.answer("\u274c Не удалось получить баланс.", reply_markup=back_keyboard())
    except Exception:
        logger.exception("Failed to fetch balance for user %s", user_id)
        await message.answer("\u274c Ошибка. Попробуй позже.", reply_markup=back_keyboard())


async def _get_balance_line(api_base_url: str, user, redis: Redis) -> str:
    from src.bot.handlers.mode_select import _get_api_headers

    balance_api = api_base_url
    user_id = user.id if hasattr(user, "id") else user
    headers = await _get_api_headers(redis, user_id, balance_api, user)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{balance_api}/api/v1/payments/balance",
                headers=headers,
            )
        if resp.status_code == 200:
            credits = resp.json().get("image_credits", 0)
            return f"\U0001f4b0 Баланс: *{credits} образов*"
    except Exception:
        logger.debug("Could not fetch balance for start message, user=%s", getattr(user, "id", user))
    return ""
