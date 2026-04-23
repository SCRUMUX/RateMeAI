"""Factory dispatch tests for the v1.21 A/B providers.

The default ``get_image_gen()`` path is already covered by
``test_factory_image_gen.py``; this module asserts that
``get_ab_image_gen(model_key)``:

- returns the right provider class for each whitelisted key
- raises on unknown keys with a helpful message
- raises when the FAL API key is missing
- caches per key (one instance per process, per model)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.providers.factory as factory


@pytest.fixture(autouse=True)
def clear_ab_cache():
    factory.get_ab_image_gen.cache_clear()
    yield
    factory.get_ab_image_gen.cache_clear()


def _fake_settings(**overrides) -> SimpleNamespace:
    base = dict(
        fal_api_key="uuid:secret",
        fal_api_host="https://queue.fal.run",
        fal_output_format="jpeg",
        fal_max_retries=2,
        fal_request_timeout=180.0,
        fal_poll_interval=1.5,
        nano_banana_model="fal-ai/nano-banana-2/edit",
        gpt_image_2_model="openai/gpt-image-2/edit",
        ab_default_quality="medium",
        ab_test_enabled=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_ab_image_models_whitelist():
    assert factory.AB_IMAGE_MODELS == frozenset(
        {"nano_banana_2", "gpt_image_2"},
    )


def test_get_ab_image_gen_nano_banana(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings())
    from src.providers.image_gen.fal_nano_banana import FalNanoBanana2Edit

    g = factory.get_ab_image_gen("nano_banana_2")
    assert isinstance(g, FalNanoBanana2Edit)


def test_get_ab_image_gen_gpt_image_2(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings())
    from src.providers.image_gen.fal_gpt_image_2 import FalGptImage2Edit

    g = factory.get_ab_image_gen("gpt_image_2")
    assert isinstance(g, FalGptImage2Edit)


def test_get_ab_image_gen_unknown_key_raises(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings())
    with pytest.raises(RuntimeError, match="unknown AB image_model"):
        factory.get_ab_image_gen("flux_42")


def test_get_ab_image_gen_normalises_casing_and_whitespace(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings())
    from src.providers.image_gen.fal_nano_banana import FalNanoBanana2Edit

    g = factory.get_ab_image_gen("  Nano_Banana_2  ")
    assert isinstance(g, FalNanoBanana2Edit)


def test_get_ab_image_gen_requires_fal_key(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings(fal_api_key=""))
    with pytest.raises(RuntimeError, match="FAL_API_KEY"):
        factory.get_ab_image_gen("nano_banana_2")


def test_get_ab_image_gen_is_cached(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings())
    a = factory.get_ab_image_gen("nano_banana_2")
    b = factory.get_ab_image_gen("nano_banana_2")
    assert a is b, "A/B provider must be cached per key"


def test_get_ab_image_gen_separate_instances_per_key(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings())
    a = factory.get_ab_image_gen("nano_banana_2")
    b = factory.get_ab_image_gen("gpt_image_2")
    assert type(a) is not type(b)
