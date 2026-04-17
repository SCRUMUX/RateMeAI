from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.providers.image_gen.reve_provider import ReveImageGen


def _fake_response(image_bytes: bytes) -> MagicMock:
    r = MagicMock()
    r.content_violation = False
    r.image_bytes = image_bytes
    r.image = Image.open(io.BytesIO(image_bytes))
    return r


@pytest.mark.asyncio
async def test_reve_image_gen_remix_returns_bytes():
    img = Image.new("RGB", (32, 32), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    fake = _fake_response(jpeg_bytes)
    gen = ReveImageGen(
        api_token="papi.test-token",
        api_host="https://api.reve.com",
    )

    with patch("reve.v1.image.remix", return_value=fake) as remix_mock:
        out = await gen.generate(
            "The subject from 0 in a studio",
            reference_image=b"\xff\xd8 fake",
            params=None,
        )

    assert len(out) > 100
    assert out == jpeg_bytes
    remix_mock.assert_called_once()
    call_kw = remix_mock.call_args
    assert call_kw[0][0] == "The subject from 0 in a studio"
    assert call_kw[0][1] == [b"\xff\xd8 fake"]


@pytest.mark.asyncio
async def test_reve_image_gen_create_without_reference():
    img = Image.new("RGB", (16, 16), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    fake = _fake_response(jpeg_bytes)

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")

    with patch("reve.v1.image.create", return_value=fake) as create_mock:
        out = await gen.generate("A red square", reference_image=None)

    assert out == jpeg_bytes
    create_mock.assert_called_once()


@pytest.mark.asyncio
async def test_reve_image_gen_no_retry_on_api_error():
    """На 5xx/ReveAPIError ретрая быть не должно: один HTTP-вызов = один биллинг."""
    from reve.exceptions import ReveAPIError

    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=3,
    )
    err = ReveAPIError("boom")
    with patch("reve.v1.image.remix", side_effect=err) as remix_mock:
        with pytest.raises(RuntimeError, match="Reve API error"):
            await gen.generate("x", reference_image=b"ref")
    assert remix_mock.call_count == 1


@pytest.mark.asyncio
async def test_reve_image_gen_retries_only_on_rate_limit():
    """429 ретраим в пределах max_retries; успешный второй вызов даёт результат."""
    from reve.exceptions import ReveRateLimitError

    img = Image.new("RGB", (8, 8), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    ok_resp = _fake_response(jpeg_bytes)

    rate_err = ReveRateLimitError("slow down")
    rate_err.retry_after = 0

    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=2,
    )
    with patch(
        "reve.v1.image.remix",
        side_effect=[rate_err, ok_resp],
    ) as remix_mock, patch("time.sleep"):
        out = await gen.generate("x", reference_image=b"ref")
    assert out == jpeg_bytes
    assert remix_mock.call_count == 2


@pytest.mark.asyncio
async def test_reve_image_gen_single_call_by_default():
    """max_retries=1 ⇒ при 429 второго вызова НЕ будет."""
    from reve.exceptions import ReveRateLimitError

    rate_err = ReveRateLimitError("slow down")
    rate_err.retry_after = 0

    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=1,
    )
    with patch(
        "reve.v1.image.remix",
        side_effect=rate_err,
    ) as remix_mock, patch("time.sleep"):
        with pytest.raises(RuntimeError, match="rate limit"):
            await gen.generate("x", reference_image=b"ref")
    assert remix_mock.call_count == 1


@pytest.mark.asyncio
async def test_reve_image_gen_uses_image_when_no_bytes():
    img = Image.new("RGB", (8, 8), color="blue")
    fake = MagicMock()
    fake.content_violation = False
    fake.image_bytes = b""
    fake.image = img

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("reve.v1.image.remix", return_value=fake):
        out = await gen.generate("x", reference_image=b"ref")
    assert out.startswith(b"\xff\xd8") or len(out) > 0
