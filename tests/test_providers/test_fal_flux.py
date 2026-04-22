from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from src.providers.image_gen.fal_flux import (
    FalAPIError,
    FalFluxImageGen,
)


def _jpeg_bytes(color=(200, 100, 40), size: int = 16) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _json_response(payload: dict, status: int = 200) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = {
        "content-type": "application/json",
        "x-fal-request-id": "fal-test-req",
    }
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
    return r


def _error_response(
    status: int,
    message: str = "bad",
    retry_after: str | None = None,
) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    hdrs = {
        "content-type": "application/json",
        "x-fal-request-id": "fal-err-req",
    }
    if retry_after is not None:
        hdrs["retry-after"] = retry_after
    r.headers = hdrs
    payload = {"detail": message}
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
    return r


def _binary_response(data: bytes) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.headers = {"content-type": "image/jpeg"}
    r.content = data
    return r


class _FakeFalClient:
    """httpx.Client double that returns queued responses.

    Each queued entry is either a MagicMock Response (returned directly)
    or an Exception (raised). The client distinguishes POST (submit) vs
    GET (status / result / image) only for assertion purposes — ordering
    of the queue is the contract callers have to honor.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _pop(self) -> object:
        if not self._responses:
            raise AssertionError("no more fake FAL responses queued")
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def post(self, url, json=None, headers=None):
        self.calls.append({
            "method": "POST", "url": url, "json": json, "headers": headers,
        })
        return self._pop()

    def get(self, url, headers=None):
        self.calls.append({
            "method": "GET", "url": url, "headers": headers,
        })
        return self._pop()


def _patched_client(fake: _FakeFalClient):
    return patch(
        "src.providers.image_gen.fal_flux.httpx.Client",
        return_value=fake,
    )


def _make_gen(**overrides) -> FalFluxImageGen:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/flux-pro/kontext",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalFluxImageGen(**defaults)


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------


def test_fal_flux_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalFluxImageGen(api_key="")


# ----------------------------------------------------------------------
# Body building
# ----------------------------------------------------------------------


def test_build_body_whitelist_and_data_uri():
    gen = _make_gen()
    ref = _jpeg_bytes()
    body = gen._build_body("put a hat on him", ref, {"seed": 42})

    assert set(body.keys()) >= {
        "prompt", "image_url", "guidance_scale",
        "num_images", "output_format", "safety_tolerance",
        "sync_mode",
    }
    assert body["prompt"] == "put a hat on him"
    assert body["sync_mode"] is True
    assert body["num_images"] == 1
    assert body["seed"] == 42
    assert body["image_url"].startswith("data:image/jpeg;base64,")
    assert base64.b64encode(ref).decode("ascii") in body["image_url"]


def test_build_body_rejects_missing_reference():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        gen._build_body("x", b"", None)


def test_build_body_passes_aspect_ratio_and_enhance_prompt():
    gen = _make_gen()
    ref = _jpeg_bytes()
    body = gen._build_body(
        "x", ref,
        {"aspect_ratio": "1:1", "enhance_prompt": True},
    )
    assert body["aspect_ratio"] == "1:1"
    assert body["enhance_prompt"] is True


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_inline_data_uri():
    out_jpeg = _jpeg_bytes((10, 20, 30), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()

    responses = [
        _json_response({"request_id": "req-abc", "status": "IN_QUEUE"}),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": data_uri, "content_type": "image/jpeg"}],
            "has_nsfw_concepts": [False],
            "seed": 123,
            "prompt": "edit",
        }),
    ]
    fake = _FakeFalClient(responses)

    gen = _make_gen()
    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        result = await gen.generate(
            "headshot on studio backdrop",
            reference_image=_jpeg_bytes(),
        )

    assert result == out_jpeg
    assert len(fake.calls) == 3
    submit, status_poll, fetch = fake.calls
    assert submit["method"] == "POST"
    assert submit["url"] == "https://queue.fal.run/fal-ai/flux-pro/kontext"
    assert submit["headers"]["Authorization"].startswith("Key ")
    assert submit["json"]["sync_mode"] is True
    assert status_poll["method"] == "GET"
    assert "requests/req-abc/status" in status_poll["url"]
    assert fetch["method"] == "GET"
    assert fetch["url"].endswith("/requests/req-abc")


@pytest.mark.asyncio
async def test_generate_fetches_external_image_url_when_not_data_uri():
    out_jpeg = _jpeg_bytes((50, 50, 50), size=24)
    image_url = "https://fal.media/files/abc/out.jpg"

    responses = [
        _json_response({"request_id": "req-xyz", "status": "IN_QUEUE"}),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": image_url, "content_type": "image/jpeg"}],
            "has_nsfw_concepts": [False],
            "seed": 1,
            "prompt": "p",
        }),
        _binary_response(out_jpeg),
    ]
    fake = _FakeFalClient(responses)

    gen = _make_gen()
    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        result = await gen.generate("p", reference_image=_jpeg_bytes())

    assert result == out_jpeg
    assert fake.calls[-1]["url"] == image_url


# ----------------------------------------------------------------------
# Error / retry behaviour
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_requires_reference_image():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        await gen.generate("x", reference_image=None)


@pytest.mark.asyncio
async def test_4xx_on_submit_no_retry():
    fake = _FakeFalClient([_error_response(400, message="bad prompt")])
    gen = _make_gen(max_retries=3)
    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="http=400") as exc_info:
            await gen.generate("p", reference_image=_jpeg_bytes())
    assert "bad prompt" in str(exc_info.value)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_401_surfaces_http_code_for_frontend_mapper():
    fake = _FakeFalClient([_error_response(401, message="invalid key")])
    gen = _make_gen(max_retries=3)
    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="http=401") as exc_info:
            await gen.generate("p", reference_image=_jpeg_bytes())
    assert "invalid key" in str(exc_info.value)


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds():
    out_jpeg = _jpeg_bytes((0, 0, 0))
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()

    responses = [
        _error_response(502, message="upstream"),
        _json_response({"request_id": "req-ok", "status": "IN_QUEUE"}),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": data_uri}],
            "has_nsfw_concepts": [False],
        }),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=2)

    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        result = await gen.generate("p", reference_image=_jpeg_bytes())

    assert result == out_jpeg
    assert fake.calls[0]["method"] == "POST"  # failed submit
    assert fake.calls[1]["method"] == "POST"  # retry submit


@pytest.mark.asyncio
async def test_queue_status_failed_raises_runtime_error():
    responses = [
        _json_response({"request_id": "req-fail", "status": "IN_QUEUE"}),
        _json_response({"status": "FAILED", "error": "model crashed"}),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=1)

    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="FAILED"):
            await gen.generate("p", reference_image=_jpeg_bytes())


@pytest.mark.asyncio
async def test_nsfw_content_violation_is_no_retry():
    responses = [
        _json_response({"request_id": "req-nsfw", "status": "IN_QUEUE"}),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": "data:image/jpeg;base64,AAAA"}],
            "has_nsfw_concepts": [True],
        }),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=3)

    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        from src.providers.image_gen.fal_flux import FalContentViolationError
        with pytest.raises(FalContentViolationError):
            await gen.generate("p", reference_image=_jpeg_bytes())
    # Must not retry a content violation.
    submit_calls = [c for c in fake.calls if c["method"] == "POST"]
    assert len(submit_calls) == 1


@pytest.mark.asyncio
async def test_missing_images_array_raises():
    responses = [
        _json_response({"request_id": "req-empty", "status": "IN_QUEUE"}),
        _json_response({"status": "COMPLETED"}),
        _json_response({"images": [], "has_nsfw_concepts": []}),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=1)

    with _patched_client(fake), patch(
        "src.providers.image_gen.fal_flux.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="no images"):
            await gen.generate("p", reference_image=_jpeg_bytes())


# ----------------------------------------------------------------------
# Low-level helpers
# ----------------------------------------------------------------------


def test_sniff_mime_detects_png_vs_jpeg():
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 8
    assert FalFluxImageGen._sniff_mime(png_header) == "image/png"
    assert FalFluxImageGen._sniff_mime(jpeg_header) == "image/jpeg"


def test_submit_missing_request_id_raises():
    """If FAL response has neither a JSON ``request_id`` nor a
    ``x-fal-request-id`` header, :meth:`_submit` must raise so the
    caller doesn't silently poll the wrong endpoint.
    """
    gen = _make_gen()
    resp = _json_response({"status": "IN_QUEUE"})
    resp.headers = {"content-type": "application/json"}  # strip the header
    fake = _FakeFalClient([resp])
    with pytest.raises(FalAPIError, match="request_id"):
        gen._submit(fake, {"prompt": "x"})
