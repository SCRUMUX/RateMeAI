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
async def test_reve_image_gen_no_retry_on_4xx_api_error():
    """4xx (не 429) не ретраим: ответ биллится, повтор не поможет."""
    from reve.exceptions import ReveAPIError

    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=3,
    )
    err = ReveAPIError("bad request")
    err.status_code = 400
    with patch("reve.v1.image.remix", side_effect=err) as remix_mock:
        with pytest.raises(RuntimeError, match="Reve API error"):
            await gen.generate("x", reference_image=b"ref")
    assert remix_mock.call_count == 1


@pytest.mark.asyncio
async def test_reve_image_gen_retries_on_5xx_then_succeeds():
    """5xx/сетевые ошибки — ответа нет, биллинга нет, ретраим в пределах max_retries."""
    from reve.exceptions import ReveAPIError

    img = Image.new("RGB", (8, 8), color="yellow")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    ok_resp = _fake_response(jpeg_bytes)

    err = ReveAPIError("upstream 500")
    err.status_code = 500

    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=2,
    )
    with patch(
        "reve.v1.image.remix",
        side_effect=[err, ok_resp],
    ) as remix_mock, patch("time.sleep"):
        out = await gen.generate("x", reference_image=b"ref")
    assert out == jpeg_bytes
    assert remix_mock.call_count == 2


@pytest.mark.asyncio
async def test_reve_image_gen_5xx_exhausts_retries():
    """При постоянных 5xx вызовов не больше max_retries."""
    from reve.exceptions import ReveAPIError

    err = ReveAPIError("upstream 502")
    err.status_code = 502

    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=2,
    )
    with patch(
        "reve.v1.image.remix",
        side_effect=err,
    ) as remix_mock, patch("time.sleep"):
        with pytest.raises(RuntimeError, match="failed after"):
            await gen.generate("x", reference_image=b"ref")
    assert remix_mock.call_count == 2


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
        with pytest.raises(RuntimeError, match="failed after"):
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


@pytest.mark.asyncio
async def test_reve_image_gen_strips_unsupported_mask_image_kwarg():
    """SDK 0.1.2 edit() does not accept `mask_image`; provider must drop it
    from kwargs instead of surfacing a TypeError."""
    img = Image.new("RGB", (16, 16), color="purple")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    fake = _fake_response(jpeg_bytes)

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("reve.v1.image.edit", return_value=fake) as edit_mock:
        out = await gen.generate(
            "studio backdrop",
            reference_image=b"\xff\xd8 fake",
            params={
                "mask_image": b"\x89PNG\r\n\x1a\n" + b"0" * 32,
                "mask_region": "background",
                "use_edit": True,
            },
        )

    assert out == jpeg_bytes
    edit_mock.assert_called_once()
    kwargs = edit_mock.call_args.kwargs
    assert "mask_image" not in kwargs, (
        "mask_image must be stripped before calling the SDK (0.1.2 does not accept it)"
    )
    assert "mask_region" not in kwargs
    assert "use_edit" not in kwargs


@pytest.mark.asyncio
async def test_reve_image_gen_applies_region_text_hint_via_mask_region():
    """`mask_region` alone (no byte-level mask) must still inject the
    'Change ONLY the background' hint at the start of the edit_instruction."""
    img = Image.new("RGB", (16, 16), color="orange")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    fake = _fake_response(jpeg_bytes)

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("reve.v1.image.edit", return_value=fake) as edit_mock:
        await gen.generate(
            "studio backdrop, soft lighting",
            reference_image=b"\xff\xd8 fake",
            params={"mask_region": "background"},
        )

    instruction = edit_mock.call_args.kwargs["edit_instruction"]
    assert instruction.startswith("Change ONLY the background"), (
        f"expected background-only hint prefix, got: {instruction!r}"
    )
    assert "studio backdrop, soft lighting" in instruction


@pytest.mark.asyncio
async def test_reve_image_gen_type_error_becomes_runtime_error():
    """Any future SDK-signature drift (unexpected kwarg) must surface as a
    RuntimeError with a clear message instead of being swallowed as a generic
    'generation_failed' upstream."""
    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch(
        "reve.v1.image.edit",
        side_effect=TypeError("edit() got an unexpected keyword argument 'foo'"),
    ):
        with pytest.raises(RuntimeError, match="Reve SDK signature mismatch"):
            await gen.generate(
                "x",
                reference_image=b"ref",
                params={"mask_region": "background"},
            )
