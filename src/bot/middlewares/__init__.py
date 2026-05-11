"""Aiogram middlewares for the two-region bot deployment."""

from src.bot.middlewares.language_guard import LanguageGuardMiddleware

__all__ = ["LanguageGuardMiddleware"]
