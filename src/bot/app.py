from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.bot.handlers import start, photo, mode_select
from src.bot.middleware import UserRegistrationMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    api_url = settings.api_base_url
    dp.message.middleware(UserRegistrationMiddleware(api_url))
    dp.callback_query.middleware(UserRegistrationMiddleware(api_url))

    dp.include_router(start.router)
    dp.include_router(photo.router)
    dp.include_router(mode_select.router)

    return dp


async def main():
    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Starting bot in polling mode...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
