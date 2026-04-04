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


def test_get_image_gen_mock_explicit(monkeypatch):
    fake = SimpleNamespace(
        image_gen_provider="mock",
        reve_api_token="",
        reve_api_host="https://api.reve.com",
        reve_aspect_ratio="1:1",
        reve_version="latest",
        reve_test_time_scaling=3,
        replicate_api_token="t",
        replicate_model_version="v",
        is_production=True,
    )
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.mock import MockImageGen

    g = factory.get_image_gen()
    assert isinstance(g, MockImageGen)


def test_get_image_gen_auto_prefers_reve(monkeypatch):
    fake = SimpleNamespace(
        image_gen_provider="auto",
        reve_api_token="papi.from-env-test",
        reve_api_host="https://api.reve.com",
        reve_aspect_ratio="1:1",
        reve_version="latest",
        reve_test_time_scaling=3,
        replicate_api_token="should_not_matter",
        replicate_model_version="also",
        is_production=True,
    )
    monkeypatch.setattr(factory, "settings", fake)
    monkeypatch.setattr(factory, "get_storage", MagicMock(return_value=MagicMock()))
    factory.get_image_gen.cache_clear()
    from src.providers.image_gen.chain import ChainImageGen
    from src.providers.image_gen.reve_provider import ReveImageGen

    g = factory.get_image_gen()
    assert isinstance(g, ChainImageGen)
    assert isinstance(g._providers[0], ReveImageGen)


def test_get_image_gen_auto_replicate_when_no_reve(monkeypatch):
    fake_st = SimpleNamespace(
        image_gen_provider="auto",
        reve_api_token="",
        reve_api_host="https://api.reve.com",
        reve_aspect_ratio="1:1",
        reve_version="latest",
        reve_test_time_scaling=3,
        replicate_api_token="r8_token",
        replicate_model_version="ver123",
        is_production=True,
    )
    monkeypatch.setattr(factory, "settings", fake_st)
    monkeypatch.setattr(
        factory,
        "get_storage",
        MagicMock(return_value=MagicMock()),
    )
    factory.get_image_gen.cache_clear()

    from src.providers.image_gen.replicate import ReplicateImageGen

    g = factory.get_image_gen()
    assert isinstance(g, ReplicateImageGen)


def test_get_image_gen_reve_prod_without_token_raises(monkeypatch):
    fake = SimpleNamespace(
        image_gen_provider="reve",
        reve_api_token="",
        reve_api_host="https://api.reve.com",
        reve_aspect_ratio="1:1",
        reve_version="latest",
        reve_test_time_scaling=3,
        replicate_api_token="",
        replicate_model_version="",
        is_production=True,
    )
    monkeypatch.setattr(factory, "settings", fake)
    factory.get_image_gen.cache_clear()

    with pytest.raises(RuntimeError, match="REVE_API_TOKEN"):
        factory.get_image_gen()
