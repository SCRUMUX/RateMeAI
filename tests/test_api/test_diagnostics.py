"""Unit tests for the diagnostics probes in ``src.api.v1.internal``.

Focus is on the two image-gen-probe modes introduced in v1.19.3:

* ``scene_preserve`` uses the synthetic solid-colour JPEG and passes
  ``generation_mode=scene_preserve`` to ``image_gen.generate``.
* ``identity_scene`` swaps in the bundled 256x256 face fixture and
  passes ``generation_mode=identity_scene``.

These tests short-circuit the auth dep and the real provider so they
run fully offline.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


def _call_probe(mode: str, fake_provider):
    """Invoke the underlying endpoint coroutine with injected provider.

    Bypasses FastAPI dependency wiring by calling the function object
    directly. Both ``image_gen_probe`` and the helper it imports live
    inside the module, so we can patch ``get_image_gen`` via
    ``monkeypatch`` on the factory.

    v1.21: ``provider`` / ``quality`` default to the pre-v1.21 styled
    router path so these tests (which predate A/B) keep exercising the
    original code path. Direct Python invocation does not run FastAPI
    Query defaults resolution, so we pass literals explicitly.
    """
    from src.api.v1 import internal as internal_mod
    from src.providers import factory as factory_mod

    original = factory_mod.get_image_gen
    factory_mod.get_image_gen = lambda: fake_provider
    try:
        result = asyncio.run(
            internal_mod.image_gen_probe(
                mode=mode, provider="styled_router", quality="low", _key="ok",
            ),
        )
    finally:
        factory_mod.get_image_gen = original
    return result


def _make_ok_provider():
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfake")
    type(provider).__name__ = "FakeImageGen"
    return provider


def test_image_gen_probe_scene_preserve_passes_generation_mode():
    provider = _make_ok_provider()
    result = _call_probe("scene_preserve", provider)

    assert result["ok"] is True
    assert result["mode"] == "scene_preserve"
    assert result["bytes"] > 0

    call = provider.generate.await_args
    assert call is not None
    kwargs = call.kwargs
    assert kwargs["params"] == {"generation_mode": "scene_preserve"}
    ref = kwargs["reference_image"]
    assert isinstance(ref, (bytes, bytearray)) and len(ref) > 0


def test_image_gen_probe_identity_scene_uses_face_fixture():
    provider = _make_ok_provider()
    result = _call_probe("identity_scene", provider)

    assert result["ok"] is True
    assert result["mode"] == "identity_scene"

    call = provider.generate.await_args
    kwargs = call.kwargs
    assert kwargs["params"] == {"generation_mode": "identity_scene"}

    ref = kwargs["reference_image"]
    assert isinstance(ref, (bytes, bytearray))
    # JPEG SOI marker — the fixture must be a real JPEG so
    # fal-ai/pulid's facexlib step can decode a face from it.
    assert bytes(ref[:3]) == b"\xff\xd8\xff"
    assert len(ref) > 5_000, (
        f"identity_scene probe fixture suspiciously small ({len(ref)} B) — "
        f"facexlib needs a real face, not a placeholder"
    )


def test_image_gen_probe_surfaces_provider_errors():
    class BoomError(RuntimeError):
        pass

    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=BoomError("upstream 422"))
    type(provider).__name__ = "FakeImageGen"

    result = _call_probe("identity_scene", provider)

    assert result["ok"] is False
    assert result["mode"] == "identity_scene"
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
