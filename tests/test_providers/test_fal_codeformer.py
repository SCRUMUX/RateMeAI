"""Unit tests for :class:`FalCodeFormerRestorer` (fal-ai/codeformer)."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from src.providers.image_gen.fal_codeformer import FalCodeFormerRestorer


def _jpeg_bytes(color=(120, 60, 30), size: int = 24) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_restorer(**overrides) -> FalCodeFormerRestorer:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/codeformer",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalCodeFormerRestorer(**defaults)


def test_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalCodeFormerRestorer(api_key="")


def test_constructor_clamps_fidelity_and_upscale():
    r = _make_restorer(fidelity=5.0, upscale_factor=9.0)
    assert r._fidelity == 1.0
    assert r._upscale_factor == 4.0


def test_body_requires_reference_image():
    r = _make_restorer()
    with pytest.raises(ValueError, match="image bytes"):
        r._build_body(prompt=None, reference_image=b"", params=None)


def test_body_has_expected_keys_and_clamps():
    r = _make_restorer(fidelity=0.5, upscale_factor=2.0)
    body = r._build_body(
        prompt=None,
        reference_image=_jpeg_bytes(),
        params={"fidelity": 3.0, "upscale_factor": 7.0, "seed": 42},
    )
    assert body["image_url"].startswith("data:image/jpeg;base64,")
    assert body["fidelity"] == 1.0  # 3.0 clamped to [0, 1]
    assert body["upscale_factor"] == 4.0  # 7.0 clamped to [1, 4]
    assert body["face_upscale"] is True
    assert body["only_center_face"] is False
    assert body["sync_mode"] is True
    assert body["seed"] == 42


def test_body_preserves_zero_fidelity():
    # fidelity=0 is the "maximum restoration" extreme — legal.
    r = _make_restorer()
    body = r._build_body(
        prompt=None,
        reference_image=_jpeg_bytes(),
        params={"fidelity": 0.0},
    )
    assert body["fidelity"] == 0.0


def test_body_no_prompt_field():
    r = _make_restorer()
    body = r._build_body(
        prompt=None, reference_image=_jpeg_bytes(), params=None,
    )
    assert "prompt" not in body
