"""Tests for bot API routing.

Since 1.62.0 there is a single bot (``@AI_Look_Studio_bot`` on
Railway) and it talks to its own region only.  The previous
two-region split with ``EDGE_API_URL`` is gone; ``_resolve_bot_api_base_url``
now always returns ``settings.api_base_url`` with any trailing slash
stripped.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def settings_clean(monkeypatch):
    from src.config import settings as _settings

    monkeypatch.setattr(_settings, "api_base_url", "http://fallback.local")
    monkeypatch.setattr(_settings, "app_env", "dev")
    return _settings


def test_bot_uses_api_base_url(settings_clean, monkeypatch):
    monkeypatch.setattr(settings_clean, "api_base_url", "https://ailookstudio.up.railway.app")
    from src.bot.app import _resolve_bot_api_base_url

    assert (
        _resolve_bot_api_base_url() == "https://ailookstudio.up.railway.app"
    )


def test_bot_strips_trailing_slash(settings_clean, monkeypatch):
    monkeypatch.setattr(
        settings_clean, "api_base_url", "https://ailookstudio.up.railway.app/"
    )
    from src.bot.app import _resolve_bot_api_base_url

    assert (
        _resolve_bot_api_base_url() == "https://ailookstudio.up.railway.app"
    )


def test_bot_uses_local_fallback_in_dev(settings_clean):
    """Without API_BASE_URL override the bot starts on the dev fallback."""
    from src.bot.app import _resolve_bot_api_base_url

    assert _resolve_bot_api_base_url() == "http://fallback.local"


def test_bot_ignores_edge_api_url_legacy(settings_clean, monkeypatch):
    """Legacy ``EDGE_API_URL`` no longer affects the resolver."""
    monkeypatch.setattr(
        settings_clean, "api_base_url", "https://ailookstudio.up.railway.app"
    )
    monkeypatch.setattr(settings_clean, "edge_api_url", "https://ailookstudio.ru")
    from src.bot.app import _resolve_bot_api_base_url

    assert (
        _resolve_bot_api_base_url() == "https://ailookstudio.up.railway.app"
    )
