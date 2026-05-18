"""Unit tests for the diagnostics probes in ``src.api.v1.internal``.

v1.64 collapsed ``image_gen_probe`` to the FAL edit-only path: the
endpoint no longer exposes ``mode`` / ``styled_router`` (those were
the pre-v1.64 PuLID / Seedream probe knobs and are gone with the
providers). The remaining surface is:

* ``provider=unified`` — default, exercises ``UnifiedImageGenProvider``.
* ``provider=gpt_image_2|nano_banana_2`` — exercises a specific
  A/B provider directly (the probe sets ``params["image_model"]``).

These tests short-circuit the auth dep and the real provider so they
run fully offline.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


def _call_probe(provider: str, fake_provider, *, quality: str = "low"):
    """Invoke the endpoint coroutine directly, bypassing FastAPI wiring.

    The endpoint resolves the image-gen provider via
    ``factory_mod.get_image_gen`` (for ``unified``) or
    ``factory_mod.get_ab_image_gen`` (for explicit A/B), so we patch
    both factories to return the same in-memory mock.
    """
    from src.api.v1 import internal as internal_mod
    from src.providers import factory as factory_mod

    original_get = factory_mod.get_image_gen
    original_ab = getattr(factory_mod, "get_ab_image_gen", None)
    factory_mod.get_image_gen = lambda: fake_provider
    factory_mod.get_ab_image_gen = lambda _key: fake_provider
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
        if original_ab is not None:
            factory_mod.get_ab_image_gen = original_ab
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


def test_image_gen_probe_explicit_ab_provider_sets_image_model():
    provider = _make_ok_provider()
    result = _call_probe("nano_banana_2", provider)

    assert result["ok"] is True
    assert result["provider_key"] == "nano_banana_2"

    call = provider.generate.await_args
    kwargs = call.kwargs
    params = kwargs.get("params") or {}
    assert params.get("image_model") == "nano_banana_2"
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
