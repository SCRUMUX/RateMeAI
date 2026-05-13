"""Aiogram middlewares for the bot.

1.62.0 — the previous ``LanguageGuardMiddleware`` (which forwarded
non-target-language users between two regional bots) was removed
together with the second bot.  The single ``@AI_Look_Studio_bot``
now serves all languages on Railway.  This package is kept so any
future middleware additions live under one stable import path.
"""

__all__: list[str] = []
