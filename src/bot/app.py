from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
from aiohttp import web
from redis.asyncio import Redis

from src.config import settings
from src.version import APP_VERSION
from src.bot.handlers import start, photo, mode_select, fallback, link
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


def _resolve_bot_api_base_url() -> str:
    """Выбор бэкенда, к которому ходит бот.

    Архитектура геосплита: на Railway (primary) живёт AI-часть, а auth /
    payments / tasks / user storage держатся на RU-edge — потому что ЮKassa
    умеет только российские IP и своя БД на RU хранит реальные балансы
    пользователей. Поэтому бот обязан ходить на EDGE_API_URL, если он задан,
    и edge сам проксирует AI-вызовы на Railway через INTERNAL_API_KEY.

    Фолбек на API_BASE_URL нужен только для dev / локального запуска (когда
    edge-сервера нет). В production без EDGE_API_URL бот работать не должен —
    мы об этом громко пишем в лог.
    """
    edge = (settings.edge_api_url or "").strip()
    if edge:
        return edge.rstrip("/")
    if settings.is_production:
        logger.error(
            "EDGE_API_URL is empty in production — bot will fall back to "
            "API_BASE_URL=%s, but /payments/* endpoints on primary return 410 "
            "and users cannot top up credits until EDGE_API_URL is configured.",
            settings.api_base_url,
        )
    return settings.api_base_url.rstrip("/")


def create_dispatcher(redis: Redis) -> Dispatcher:
    dp = Dispatcher()
    api_url = _resolve_bot_api_base_url()
    dp.message.middleware(UserRegistrationMiddleware(api_url, redis))
    dp.callback_query.middleware(UserRegistrationMiddleware(api_url, redis))

    dp.include_router(start.router)
    dp.include_router(link.router)
    dp.include_router(photo.router)
    dp.include_router(mode_select.router)
    dp.include_router(fallback.router)  # must be last — catch-all

    @dp.error()
    async def on_handler_error(event: ErrorEvent) -> bool:
        logger.exception("Unhandled error in handler: %s", event.exception)
        update = event.update
        try:
            if update.message:
                await update.message.answer(
                    "\u274c Произошла ошибка. Попробуй ещё раз или отправь /start",
                    parse_mode=None,
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    "Произошла ошибка. Попробуй ещё раз.",
                    show_alert=True,
                )
        except Exception:
            logger.debug("Could not send error reply to user")
        return True

    return dp


async def _health_handler(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "bot", "version": APP_VERSION})


async def _start_health_server(app: web.Application | None = None) -> None:
    """Start a minimal HTTP server for Railway health checks."""
    if app is None:
        app = web.Application()
    app.router.add_get("/health", _health_handler)
    port = int(os.environ.get("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


async def main():
    sha = (settings.deploy_git_sha or "").strip()
    logger.info(
        "Telegram bot starting RateMeAI version=%s market=%s role=%s compute=%s%s",
        APP_VERSION,
        settings.resolved_market_id,
        settings.resolved_service_role,
        settings.resolved_compute_mode,
        f" git={sha[:12]}" if sha else "",
    )
    bot_api_url = _resolve_bot_api_base_url()
    logger.info(
        "Bot traffic pinned to %s (edge_api_url=%s, api_base_url=%s) — "
        "auth/payments/tasks live on RU-edge, AI is proxied to primary.",
        bot_api_url, settings.edge_api_url or "<empty>", settings.api_base_url,
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
        )

        app = web.Application()
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.bot_webhook_secret or None,
        ).register(app, path=wh_path)
        setup_application(app, dp, bot=bot)

        await _start_health_server(app)
        logger.info("Bot webhook listening on 0.0.0.0:%s%s", int(os.environ.get("PORT", "8080")), wh_path)
        await asyncio.Event().wait()
    else:
        await _start_health_server()
        logger.info("Bot health server started on 0.0.0.0:%s", os.environ.get("PORT", "8080"))
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook deleted, waiting for old instances to release polling lock...")
        await asyncio.sleep(3)
        logger.info("Starting bot in polling mode (single replica recommended).")
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message", "callback_query", "edited_message",
                "channel_post", "inline_query",
            ],
        )


if __name__ == "__main__":
    asyncio.run(main())
