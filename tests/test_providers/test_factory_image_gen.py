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
        reve_version="latest",
        reve_max_retries=1,
        replicate_api_token="",
        replicate_model_version="",
        fal_api_key="",
        fal_model="fal-ai/flux-pro/kontext",
        fal_api_host="https://queue.fal.run",
        fal_guidance_scale=3.5,
        fal_safety_tolerance="2",
        fal_output_format="jpeg",
        fal_max_retries=2,
        fal_request_timeout=180.0,
        fal_poll_interval=1.5,
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


def test_get_image_gen_auto_prefers_fal_over_reve(monkeypatch):
    """auto — FAL ключ приоритетнее Reve. Нужно для безболезненного
    переключения стека на FLUX для лицевых сценариев без изменения
    IMAGE_GEN_PROVIDER в каждом окружении.
    """
    fake = _fake_settings(
        image_gen_provider="auto",
        fal_api_key="uuid:secret",
        reve_api_token="papi.should-not-be-used",
    )
    monkeypatch.setattr(factory, "settings", fake)
    monkeypatch.setattr(factory, "get_storage", MagicMock(return_value=MagicMock()))
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.fal_flux import FalFluxImageGen
    from src.providers.image_gen.reve_provider import ReveImageGen

    g = factory.get_image_gen()
    assert isinstance(g, FalFluxImageGen)
    assert not isinstance(g, ReveImageGen)


def test_get_image_gen_auto_falls_back_to_reve(monkeypatch):
    """auto — без FAL_API_KEY должен откатываться на Reve, если REVE_API_TOKEN есть."""
    fake = _fake_settings(
        image_gen_provider="auto",
        fal_api_key="",
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


def test_get_image_gen_auto_prod_without_keys_raises(monkeypatch):
    """В prod при отсутствии FAL_API_KEY и REVE_API_TOKEN auto-режим должен падать."""
    fake = _fake_settings(
        image_gen_provider="auto",
        fal_api_key="",
        reve_api_token="",
        replicate_api_token="r8_token",
        replicate_model_version="ver123",
    )
    monkeypatch.setattr(factory, "settings", fake)
    monkeypatch.setattr(factory, "get_storage", MagicMock(return_value=MagicMock()))
    factory.get_image_gen.cache_clear()

    with pytest.raises(RuntimeError, match="FAL_API_KEY or REVE_API_TOKEN"):
        factory.get_image_gen()


def test_get_image_gen_reve_prod_without_token_raises(monkeypatch):
    fake = _fake_settings(image_gen_provider="reve", reve_api_token="")
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()

    with pytest.raises(RuntimeError, match="REVE_API_TOKEN"):
        factory.get_image_gen()


def test_get_image_gen_fal_flux_explicit(monkeypatch):
    fake = _fake_settings(
        image_gen_provider="fal_flux",
        fal_api_key="uuid:secret",
    )
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.fal_flux import FalFluxImageGen

    g = factory.get_image_gen()
    assert isinstance(g, FalFluxImageGen)


def test_get_image_gen_fal_flux_prod_without_key_raises(monkeypatch):
    fake = _fake_settings(image_gen_provider="fal_flux", fal_api_key="")
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()

    with pytest.raises(RuntimeError, match="FAL_API_KEY"):
        factory.get_image_gen()


def test_get_image_gen_fal_flux_dev_without_key_falls_back_to_mock(monkeypatch):
    fake = _fake_settings(
        image_gen_provider="fal_flux", fal_api_key="", is_production=False,
    )
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.mock import MockImageGen

    g = factory.get_image_gen()
    assert isinstance(g, MockImageGen)
