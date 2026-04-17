from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.providers.factory as factory


@pytest.fixture(autouse=True)
def clear_image_gen_cache():
    factory.get_image_gen.cache_clear()
    yield
    factory.get_image_gen.cache_clear()


def _fake_settings(**overrides):
    base = dict(
        image_gen_provider="mock",
        reve_api_token="",
        reve_api_host="https://api.reve.com",
        reve_aspect_ratio="1:1",
        reve_version="latest",
        reve_test_time_scaling=3,
        reve_max_retries=1,
        replicate_api_token="",
        replicate_model_version="",
        is_production=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_get_image_gen_mock_explicit(monkeypatch):
    fake = _fake_settings(
        image_gen_provider="mock",
        replicate_api_token="t",
        replicate_model_version="v",
    )
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.mock import MockImageGen

    g = factory.get_image_gen()
    assert isinstance(g, MockImageGen)


def test_get_image_gen_auto_uses_reve_only(monkeypatch):
    """Replicate временно отключён: auto должен возвращать ReveImageGen напрямую,
    без ChainImageGen, даже если Replicate-ключи настроены."""
    fake = _fake_settings(
        image_gen_provider="auto",
        reve_api_token="papi.from-env-test",
        replicate_api_token="should_not_matter",
        replicate_model_version="also",
    )
    monkeypatch.setattr(factory, "settings", fake)
    monkeypatch.setattr(factory, "get_storage", MagicMock(return_value=MagicMock()))
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.reve_provider import ReveImageGen
    from src.providers.image_gen.chain import ChainImageGen

    g = factory.get_image_gen()
    assert isinstance(g, ReveImageGen)
    assert not isinstance(g, ChainImageGen)


def test_get_image_gen_auto_prod_without_reve_raises(monkeypatch):
    """В prod при отсутствии REVE_API_TOKEN auto-режим должен падать,
    потому что Replicate как fallback больше не используется."""
    fake = _fake_settings(
        image_gen_provider="auto",
        reve_api_token="",
        replicate_api_token="r8_token",
        replicate_model_version="ver123",
    )
    monkeypatch.setattr(factory, "settings", fake)
    monkeypatch.setattr(factory, "get_storage", MagicMock(return_value=MagicMock()))
    factory.get_image_gen.cache_clear()

    with pytest.raises(RuntimeError, match="REVE_API_TOKEN"):
        factory.get_image_gen()


def test_get_image_gen_reve_prod_without_token_raises(monkeypatch):
    fake = _fake_settings(image_gen_provider="reve", reve_api_token="")
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()

    with pytest.raises(RuntimeError, match="REVE_API_TOKEN"):
        factory.get_image_gen()
