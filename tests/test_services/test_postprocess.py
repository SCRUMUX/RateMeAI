"""Local PIL post-processing (crop_to_aspect + upscale_lanczos) tests.

These replace Reve's server-side ``postprocessing`` field (which the
REST API does not accept) and the ``aspect_ratio`` field on the edit
endpoint. Keeping them purely local means zero extra bytes in the
Reve request body.
"""

from __future__ import annotations

import io

from PIL import Image

from src.services.postprocess import crop_to_aspect, upscale_lanczos


def _png(w: int, h: int, color: tuple[int, int, int] = (128, 128, 128)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def test_crop_to_aspect_3x4_from_square():
    src = _png(1024, 1024)
    out = crop_to_aspect(src, "3:4")
    w, h = _size(out)
    ratio = w / h
    assert abs(ratio - 3 / 4) < 0.01


def test_crop_to_aspect_2x3_from_landscape():
    src = _png(1600, 1000)
    out = crop_to_aspect(src, "2:3")
    w, h = _size(out)
    ratio = w / h
    assert abs(ratio - 2 / 3) < 0.01


def test_crop_to_aspect_1x1_from_portrait():
    src = _png(900, 1600)
    out = crop_to_aspect(src, "1:1")
    w, h = _size(out)
    assert abs(w - h) <= 1


def test_crop_to_aspect_same_ratio_returns_original_bytes():
    src = _png(900, 1200)
    out = crop_to_aspect(src, "3:4")
    assert out == src


def test_crop_to_aspect_invalid_returns_original_bytes():
    src = _png(800, 600)
    assert crop_to_aspect(src, "not-an-ar") == src
    assert crop_to_aspect(src, "") == src
    assert crop_to_aspect(src, "0:5") == src


def test_crop_to_aspect_returns_png():
    src = _png(1024, 1024)
    out = crop_to_aspect(src, "3:4")
    assert out[:8] == b"\x89PNG\r\n\x1a\n"


def test_upscale_lanczos_doubles_dimensions():
    src = _png(300, 200)
    out = upscale_lanczos(src, factor=2)
    w, h = _size(out)
    assert (w, h) == (600, 400)


def test_upscale_lanczos_factor_one_is_noop():
    src = _png(300, 200)
    out = upscale_lanczos(src, factor=1)
    assert out == src


def test_upscale_lanczos_bad_input_returns_original():
    assert upscale_lanczos(b"not-an-image", factor=2) == b"not-an-image"


def test_upscale_lanczos_returns_png():
    src = _png(100, 150)
    out = upscale_lanczos(src, factor=2)
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
