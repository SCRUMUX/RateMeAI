"""Unit tests for :class:`FalSeedreamImageGen` (fal-ai/bytedance/seedream/v4/edit)."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from src.providers.image_gen.fal_seedream import FalSeedreamImageGen


def _jpeg_bytes(color=(80, 90, 100), size: int = 24) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_gen(**overrides) -> FalSeedreamImageGen:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/bytedance/seedream/v4/edit",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalSeedreamImageGen(**defaults)


def test_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalSeedreamImageGen(api_key="")


def test_body_uses_image_urls_list_no_flux_specific_fields():
    gen = _make_gen()
    ref = _jpeg_bytes()
    body = gen._build_body("polish the scene", ref, {"seed": 7})

    assert isinstance(body["image_urls"], list)
    assert len(body["image_urls"]) == 1
    assert body["image_urls"][0].startswith("data:image/jpeg;base64,")
    assert base64.b64encode(ref).decode("ascii") in body["image_urls"][0]

    assert body["prompt"] == "polish the scene"
    assert body["num_images"] == 1
    assert body["seed"] == 7
    assert body["enable_safety_checker"] is True
    assert body["enhance_prompt_mode"] == "standard"

    for forbidden in (
        "safety_tolerance",
        "output_format",
        "guidance_scale",
        "reference_images",
        "image_url",
    ):
        assert forbidden not in body


def test_body_rejects_missing_reference():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        gen._build_body("x", b"", None)


def test_body_rejects_unknown_enhance_mode_falls_back_to_standard():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"enhance_prompt_mode": "turbo"},
    )
    assert body["enhance_prompt_mode"] == "standard"


def test_body_accepts_fast_enhance_mode():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"enhance_prompt_mode": "fast"},
    )
    assert body["enhance_prompt_mode"] == "fast"


def test_body_default_image_size_is_portrait_4_3():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), None)
    assert body["image_size"] == "portrait_4_3"


def test_body_accepts_custom_image_size_dict():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"image_size": {"width": 2048, "height": 2048}},
    )
    assert body["image_size"] == {"width": 2048, "height": 2048}


def test_body_accepts_extra_reference_images():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"extra_reference_images": [_jpeg_bytes(color=(1, 2, 3))]},
    )
    assert len(body["image_urls"]) == 2


def test_body_caps_reference_images_to_ten():
    gen = _make_gen()
    extras = [_jpeg_bytes(color=(i, i, i)) for i in range(20)]
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"extra_reference_images": extras},
    )
    assert len(body["image_urls"]) == 10
