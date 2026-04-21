from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from src.providers.image_gen.reve_provider import (
    ReveAPIError,
    ReveImageGen,
    ReveRateLimitError,
)


def _jpeg_bytes(color: str | tuple = "red", size: int = 16) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _response_image(image_bytes: bytes, status: int = 200) -> MagicMock:
    """Fake httpx.Response returning a base64-image JSON payload."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = {
        "content-type": "application/json",
        "x-reve-request-id": "rsid-test",
        "x-reve-content-violation": "false",
    }
    payload = {"image": base64.b64encode(image_bytes).decode("ascii")}
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
    return r


def _response_error(
    status: int,
    message: str = "error",
    error_code: str | None = None,
    retry_after: str | None = None,
) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    hdrs = {
        "content-type": "application/json",
        "x-reve-request-id": "rsid-err",
    }
    if error_code:
        hdrs["x-reve-error-code"] = error_code
    if retry_after is not None:
        hdrs["retry-after"] = retry_after
    r.headers = hdrs
    payload = {"error_code": error_code or "ERR", "message": message}
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
    return r


class _FakeClient:
    """Minimal httpx.Client replacement that returns a queued response."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _patch_client(responses):
    fake = _FakeClient(responses)
    return patch("src.providers.image_gen.reve_provider.httpx.Client",
                 return_value=fake), fake


@pytest.mark.asyncio
async def test_reve_image_gen_remix_returns_bytes():
    jpeg = _jpeg_bytes(color=(128, 64, 32), size=32)
    fake = _FakeClient([_response_image(jpeg)])

    gen = ReveImageGen(api_token="papi.test-token", api_host="https://api.reve.com")
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake):
        out = await gen.generate(
            "The subject from 0 in a studio",
            reference_image=b"\xff\xd8 fake",
            params=None,
        )

    assert out == jpeg
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"].endswith("/v1/image/remix")
    assert call["json"]["prompt"] == "The subject from 0 in a studio"
    assert isinstance(call["json"]["reference_images"], list)
    assert call["json"]["reference_images"][0] == base64.b64encode(
        b"\xff\xd8 fake"
    ).decode("ascii")
    assert call["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_reve_image_gen_create_without_reference():
    jpeg = _jpeg_bytes("red")
    fake = _FakeClient([_response_image(jpeg)])

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake):
        out = await gen.generate("A red square", reference_image=None)

    assert out == jpeg
    assert fake.calls[0]["url"].endswith("/v1/image/create")
    assert "reference_images" not in fake.calls[0]["json"]


@pytest.mark.asyncio
async def test_reve_image_gen_no_retry_on_4xx_api_error():
    """4xx (not 429) must surface as RuntimeError without retry."""
    fake = _FakeClient([
        _response_error(400, message="bad request", error_code="BAD_REQUEST"),
    ])
    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=3,
    )
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake), patch(
                   "src.providers.image_gen.reve_provider.time.sleep"):
        with pytest.raises(RuntimeError, match="http=400") as exc_info:
            await gen.generate("x", reference_image=b"ref")
        assert "Reve API error" in str(exc_info.value)
        assert "bad request" in str(exc_info.value)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_reve_image_gen_401_includes_http_code_for_frontend_mapper():
    """401 (expired partner token) must contain 'http=401' — the frontend
    mapper relies on that substring to route into PROVIDER_AUTH_MESSAGE."""
    fake = _FakeClient([
        _response_error(401, message="Invalid partner API bearer token.",
                        error_code="PARTNER_API_TOKEN_INVALID"),
    ])
    gen = ReveImageGen(
        api_token="papi.expired",
        api_host="https://api.reve.com",
        max_retries=3,
    )
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake), patch(
                   "src.providers.image_gen.reve_provider.time.sleep"):
        with pytest.raises(RuntimeError, match="http=401") as exc_info:
            await gen.generate("prompt")
        assert "Invalid partner API bearer token" in str(exc_info.value)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_reve_image_gen_retries_on_5xx_then_succeeds():
    """5xx / transport errors are retried within max_retries."""
    jpeg = _jpeg_bytes("yellow")
    fake = _FakeClient([
        _response_error(500, message="upstream 500"),
        _response_image(jpeg),
    ])
    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=2,
    )
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake), patch(
                   "src.providers.image_gen.reve_provider.time.sleep"):
        out = await gen.generate("x", reference_image=b"ref")
    assert out == jpeg
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_reve_image_gen_5xx_exhausts_retries():
    fake = _FakeClient([
        _response_error(502, message="upstream 502"),
        _response_error(502, message="upstream 502"),
    ])
    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=2,
    )
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake), patch(
                   "src.providers.image_gen.reve_provider.time.sleep"):
        with pytest.raises(RuntimeError, match="failed after"):
            await gen.generate("x", reference_image=b"ref")
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_reve_image_gen_retries_only_on_rate_limit():
    """429 is retried within max_retries."""
    jpeg = _jpeg_bytes("green")
    fake = _FakeClient([
        _response_error(429, message="slow down",
                        error_code="PARTNER_API_TOKEN_RATE_LIMIT_EXCEEDED",
                        retry_after="0"),
        _response_image(jpeg),
    ])
    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=2,
    )
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake), patch(
                   "src.providers.image_gen.reve_provider.time.sleep"):
        out = await gen.generate("x", reference_image=b"ref")
    assert out == jpeg
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_reve_image_gen_single_call_by_default():
    """max_retries=1 ⇒ 429 terminates after a single call."""
    fake = _FakeClient([
        _response_error(429, message="slow down",
                        error_code="PARTNER_API_TOKEN_RATE_LIMIT_EXCEEDED",
                        retry_after="0"),
    ])
    gen = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        max_retries=1,
    )
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake), patch(
                   "src.providers.image_gen.reve_provider.time.sleep"):
        with pytest.raises(RuntimeError, match="failed after"):
            await gen.generate("x", reference_image=b"ref")
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_reve_image_gen_handles_empty_image_field():
    """If the API unexpectedly returns an empty image field, surface a
    RuntimeError instead of silently returning b''."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.headers = {"content-type": "application/json", "x-reve-request-id": "x"}
    r.content = b'{"image":""}'
    r.text = '{"image":""}'
    r.json = MagicMock(return_value={"image": ""})

    fake = _FakeClient([r])

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake):
        with pytest.raises(RuntimeError):
            await gen.generate("x", reference_image=b"ref")


@pytest.mark.asyncio
async def test_reve_image_gen_applies_region_text_hint_via_mask_region():
    """`mask_region` alone must prefix the edit_instruction with the hint."""
    jpeg = _jpeg_bytes("orange")
    fake = _FakeClient([_response_image(jpeg)])

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake):
        await gen.generate(
            "studio backdrop, soft lighting",
            reference_image=b"\xff\xd8 fake",
            params={"mask_region": "background"},
        )

    call = fake.calls[0]
    assert call["url"].endswith("/v1/image/edit")
    instruction = call["json"]["edit_instruction"]
    assert instruction.startswith("Change ONLY the background"), (
        f"expected background-only hint prefix, got: {instruction!r}"
    )
    assert "studio backdrop, soft lighting" in instruction


@pytest.mark.asyncio
async def test_reve_image_gen_strips_unsupported_mask_image_kwarg():
    """mask_image / mask_region / use_edit are internal — never sent to Reve."""
    jpeg = _jpeg_bytes("purple")
    fake = _FakeClient([_response_image(jpeg)])

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake):
        out = await gen.generate(
            "studio backdrop",
            reference_image=b"\xff\xd8 fake",
            params={
                "mask_image": b"\x89PNG\r\n\x1a\n" + b"0" * 32,
                "mask_region": "background",
                "use_edit": True,
            },
        )

    assert out == jpeg
    payload = fake.calls[0]["json"]
    assert "mask_image" not in payload
    assert "mask_region" not in payload
    assert "use_edit" not in payload


@pytest.mark.asyncio
async def test_reve_image_gen_content_violation_surfaces_error():
    """Content-policy violation flagged in the response body must raise."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.headers = {
        "content-type": "application/json",
        "x-reve-request-id": "rsid-cv",
        "x-reve-content-violation": "true",
    }
    payload = {"content_violation": True, "message": "blocked"}
    body = json.dumps(payload).encode()
    r.content = body
    r.text = body.decode()
    r.json = MagicMock(return_value=payload)

    fake = _FakeClient([r])

    gen = ReveImageGen(api_token="papi.x", api_host="https://api.reve.com")
    with patch("src.providers.image_gen.reve_provider.httpx.Client",
               return_value=fake):
        with pytest.raises(Exception) as exc_info:
            await gen.generate("x", reference_image=b"ref")
        assert "content policy" in str(exc_info.value).lower()


def test_reve_api_error_module_exports():
    """Make sure the custom error classes are importable by name."""
    assert issubclass(ReveRateLimitError, ReveAPIError)
