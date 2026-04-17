"""Tests for bot API routing.

Геосплит требует, чтобы бот ходил за auth / payments / tasks на RU-edge,
а не на Railway primary. Ядро логики — `_resolve_bot_api_base_url` в
`src/bot/app.py`. Этот тест защищает от регрессии, как только что была:
бот был хардкодно прибит к `API_BASE_URL`, из-за чего в production
создавались тестовые платежи ЮKassa и балансы «исчезали» (они лежали в
RU БД, а бот читал Railway БД).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def settings_clean(monkeypatch):
    from src.config import settings as _settings
    monkeypatch.setattr(_settings, "edge_api_url", "")
    monkeypatch.setattr(_settings, "api_base_url", "http://fallback.local")
    monkeypatch.setattr(_settings, "app_env", "dev")
    return _settings


def test_bot_uses_edge_api_when_configured(settings_clean, monkeypatch):
    monkeypatch.setattr(settings_clean, "edge_api_url", "https://ru.ailookstudio.ru")
    from src.bot.app import _resolve_bot_api_base_url
    assert _resolve_bot_api_base_url() == "https://ru.ailookstudio.ru"


def test_bot_strips_trailing_slash(settings_clean, monkeypatch):
    monkeypatch.setattr(settings_clean, "edge_api_url", "https://ru.ailookstudio.ru/")
    from src.bot.app import _resolve_bot_api_base_url
    assert _resolve_bot_api_base_url() == "https://ru.ailookstudio.ru"


def test_bot_falls_back_to_api_base_url_in_dev(settings_clean):
    """Без EDGE_API_URL бот всё ещё должен стартовать (dev / локальный запуск)."""
    from src.bot.app import _resolve_bot_api_base_url
    assert _resolve_bot_api_base_url() == "http://fallback.local"


def test_bot_logs_error_if_edge_missing_in_production(settings_clean, monkeypatch, caplog):
    """В проде без EDGE_API_URL валимся в лог, чтобы это было видно на деплое.

    Без этого сигнала деплой «успешный», но бот ходит на primary и снова
    упирается в 410 / тестовые платежи.
    """
    monkeypatch.setattr(settings_clean, "app_env", "prod")
    import logging
    from src.bot.app import _resolve_bot_api_base_url
    with caplog.at_level(logging.ERROR, logger="src.bot.app"):
        url = _resolve_bot_api_base_url()
    assert url == "http://fallback.local"
    assert any("EDGE_API_URL is empty in production" in rec.message for rec in caplog.records)
