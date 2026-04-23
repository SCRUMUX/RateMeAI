"""Unit tests for :class:`FalRealEsrganUpscaler`.

Mirrors the GFPGAN test surface: same queue-based wire protocol, same
error semantics, different payload shape. We cover:

* body shape — ``image_url`` + ``scale`` (clamped to {2, 3, 4});
* happy path via an inline base64 data URI;
* external image URL fetch path (result payload ⇒ follow-up GET);
* 4xx on submit → ``RuntimeError`` with the HTTP status surfaced.
"""

from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from src.providers.image_gen.fal_esrgan import FalRealEsrganUpscaler


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
        "x-fal-request-id": "esr-req",
    }
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
    return r


def _error_response(status: int, message: str = "bad") -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = {
        "content-type": "application/json",
        "x-fal-request-id": "esr-err",
    }
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
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _pop(self):
        if not self._responses:
            raise AssertionError("no more fake FAL responses queued")
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def post(self, url, json=None, headers=None):
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "json": json,
                "headers": headers,
            }
        )
        return self._pop()

    def get(self, url, headers=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        return self._pop()


def _patched_client(fake: _FakeFalClient):
    return patch(
        "src.providers.image_gen._fal_queue_base.httpx.Client",
        return_value=fake,
    )


def _make_upscaler(**overrides) -> FalRealEsrganUpscaler:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/real-esrgan",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalRealEsrganUpscaler(**defaults)


def test_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalRealEsrganUpscaler(api_key="")


def test_body_shape_is_single_image_url_with_scale():
    u = _make_upscaler()
    body = u._build_body(reference_image=_jpeg_bytes(), params={"scale": 2})
    assert isinstance(body["image_url"], str)
    assert body["image_url"].startswith("data:image/jpeg;base64,")
    assert body["scale"] == 2
    assert body.get("sync_mode") is True


def test_body_clamps_unsupported_scale_to_two():
    u = _make_upscaler()
    body = u._build_body(reference_image=_jpeg_bytes(), params={"scale": 7})
    assert body["scale"] == 2


@pytest.mark.asyncio
async def test_upscale_happy_path_inline_data_uri():
    out_jpeg = _jpeg_bytes((30, 30, 30), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()
    status_url = "https://queue.fal.run/fal-ai/real-esrgan/requests/r/status"
    response_url = "https://queue.fal.run/fal-ai/real-esrgan/requests/r"
    responses = [
        _json_response(
            {
                "request_id": "r",
                "status": "IN_QUEUE",
                "status_url": status_url,
                "response_url": response_url,
            }
        ),
        _json_response({"status": "COMPLETED"}),
        _json_response(
            {
                "image": {"url": data_uri},
                "has_nsfw_concepts": [False],
            }
        ),
    ]
    fake = _FakeFalClient(responses)

    upscaler = _make_upscaler()
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        out = await upscaler.upscale(_jpeg_bytes(), factor=2)

    assert out == out_jpeg
    assert fake.calls[0]["url"] == "https://queue.fal.run/fal-ai/real-esrgan"


@pytest.mark.asyncio
async def test_upscale_follows_external_image_url():
    out_jpeg = _jpeg_bytes((10, 120, 10), size=24)
    external = "https://fal.media/files/abc/upscaled.jpg"
    responses = [
        _json_response(
            {
                "request_id": "x",
                "status": "IN_QUEUE",
                "status_url": "https://queue.fal.run/fal-ai/real-esrgan/requests/x/status",
                "response_url": "https://queue.fal.run/fal-ai/real-esrgan/requests/x",
            }
        ),
        _json_response({"status": "COMPLETED"}),
        _json_response(
            {
                "image": {"url": external},
                "has_nsfw_concepts": [False],
            }
        ),
        _binary_response(out_jpeg),
    ]
    fake = _FakeFalClient(responses)

    upscaler = _make_upscaler()
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        out = await upscaler.upscale(_jpeg_bytes())

    assert out == out_jpeg
    assert fake.calls[-1]["url"] == external


@pytest.mark.asyncio
async def test_upscale_4xx_on_submit_no_retry():
    fake = _FakeFalClient([_error_response(400, "bad")])
    upscaler = _make_upscaler(max_retries=3)
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="http=400"):
            await upscaler.upscale(_jpeg_bytes())
    assert len(fake.calls) == 1
