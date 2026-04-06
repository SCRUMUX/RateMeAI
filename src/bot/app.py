from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web
from redis.asyncio import Redis

from src.config import settings
from src.version import APP_VERSION
from src.bot.handlers import start, photo, mode_select, fallback
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


def create_dispatcher(redis: Redis) -> Dispatcher:
    dp = Dispatcher()
    api_url = settings.api_base_url
    dp.message.middleware(UserRegistrationMiddleware(api_url, redis))
    dp.callback_query.middleware(UserRegistrationMiddleware(api_url, redis))

    dp.include_router(start.router)
    dp.include_router(photo.router)
    dp.include_router(mode_select.router)
    dp.include_router(fallback.router)  # must be last — catch-all

    return dp


async def main():
    sha = (settings.deploy_git_sha or "").strip()
    logger.info(
        "Telegram bot starting RateMeAI version=%s%s",
        APP_VERSION,
        f" git={sha[:12]}" if sha else "",
    )
    bot = create_bot()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    dp = create_dispatcher(redis)

    if settings.bot_webhook_url:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        parsed = urlparse(settings.bot_webhook_url)
        wh_path = parsed.path or "/webhook"
        webhook_full_url = f"{parsed.scheme}://{parsed.netloc}{wh_path}"

        await bot.set_webhook(
            webhook_full_url,
            secret_token=settings.bot_webhook_secret or None,
            drop_pending_updates=True,
        )

        app = web.Application()
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.bot_webhook_secret or None,
        ).register(app, path=wh_path)
        setup_application(app, dp, bot=bot)

        port = int(os.environ.get("PORT", "8080"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Bot webhook listening on 0.0.0.0:%s%s", port, wh_path)
        await asyncio.Event().wait()
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting bot in polling mode (single replica recommended).")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
