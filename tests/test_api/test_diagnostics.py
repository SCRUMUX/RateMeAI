"""Unit tests for the diagnostics probes in ``src.api.v1.internal``.

Post Nano-Banana cleanup ``image_gen_probe`` exposes two accepted
``provider`` values — ``unified`` and ``gpt_image_2`` — both
resolving to the single GPT Image 2 backend. The alias survives so
historical curl scripts / Railway health probes keep working.

These tests short-circuit the auth dep and the real provider so they
run fully offline.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


def _call_probe(provider: str, fake_provider, *, quality: str = "low"):
    """Invoke the endpoint coroutine directly, bypassing FastAPI wiring.

    The endpoint resolves the image-gen provider via the single
    ``factory_mod.get_image_gen`` (since v1.70.15), so we patch
    that one factory to return the in-memory mock.
    """
    from src.api.v1 import internal as internal_mod
    from src.providers import factory as factory_mod

    original_get = factory_mod.get_image_gen
    factory_mod.get_image_gen = lambda: fake_provider
    try:
        result = asyncio.run(
            internal_mod.image_gen_probe(
                provider=provider,
                quality=quality,
                _key="ok",
            ),
        )
    finally:
        factory_mod.get_image_gen = original_get
    return result


def _make_ok_provider():
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfake")
    type(provider).__name__ = "FakeImageGen"
    return provider


def test_image_gen_probe_unified_uses_face_fixture():
    provider = _make_ok_provider()
    result = _call_probe("unified", provider)

    assert result["ok"] is True
    assert result["provider_key"] == "unified"
    assert result["bytes"] > 0

    call = provider.generate.await_args
    assert call is not None
    kwargs = call.kwargs

    # Unified path does not pre-set ``image_model`` — the provider
    # itself picks Model A as the default.
    params = kwargs.get("params") or {}
    assert "image_model" not in params
    assert params.get("quality") == "low"

    ref = kwargs["reference_image"]
    assert isinstance(ref, (bytes, bytearray))
    # JPEG SOI marker — the fixture must be a real JPEG so the FAL
    # edit-model's face detector can decode a face from it.
    assert bytes(ref[:3]) == b"\xff\xd8\xff"
    assert len(ref) > 5_000, (
        f"probe face fixture suspiciously small ({len(ref)} B) — "
        f"face detectors need a real face, not a placeholder"
    )


def test_image_gen_probe_explicit_gpt_image_2_sets_image_model():
    """Pinning ``provider=gpt_image_2`` writes the label into
    ``params["image_model"]`` so the probe matches the production
    request shape for the single-provider path."""
    provider = _make_ok_provider()
    result = _call_probe("gpt_image_2", provider)

    assert result["ok"] is True
    assert result["provider_key"] == "gpt_image_2"

    call = provider.generate.await_args
    kwargs = call.kwargs
    params = kwargs.get("params") or {}
    assert params.get("image_model") == "gpt_image_2"
    assert params.get("quality") == "low"


def test_image_gen_probe_surfaces_provider_errors():
    class BoomError(RuntimeError):
        pass

    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=BoomError("upstream 422"))
    type(provider).__name__ = "FakeImageGen"

    result = _call_probe("unified", provider)

    assert result["ok"] is False
    assert result["provider_key"] == "unified"
    assert result["exc_type"] == "BoomError"
    assert "upstream 422" in (result.get("repr") or "")


def test_probe_face_fixture_decodes_to_jpeg():
    """The fixture must be a real 256x256 JPEG, not a stub."""
    from io import BytesIO

    from PIL import Image

    from src.api.v1._fixtures.probe_face import probe_face_jpeg

    raw = probe_face_jpeg()
    assert bytes(raw[:3]) == b"\xff\xd8\xff"

    img = Image.open(BytesIO(raw))
    assert img.format == "JPEG"
    assert img.size == (256, 256)
