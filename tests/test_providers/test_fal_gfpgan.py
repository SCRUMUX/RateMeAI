"""Unit tests for :class:`FalGfpganRestorer`.

The wire protocol (queue submit → status poll → result fetch → decode)
mirrors :class:`FalFlux2ImageGen`, so we keep the coverage tight and
focus on the GFPGAN-specific bits:

* body shape — a single ``image_url`` (not the FLUX ``image_urls``
  list), no prompt, no seed;
* happy-path decoding from an inline ``data:image/...;base64`` URL;
* NSFW → ``FalContentViolationError`` (no retry);
* 4xx on submit → ``RuntimeError`` (no retry) with the HTTP status
  surfaced.
"""
from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from src.providers.image_gen.fal_flux import FalContentViolationError
from src.providers.image_gen.fal_gfpgan import FalGfpganRestorer


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
        "x-fal-request-id": "gfp-req",
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
        "x-fal-request-id": "gfp-err",
    }
    payload = {"detail": message}
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
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
        self.calls.append({
            "method": "POST", "url": url, "json": json, "headers": headers,
        })
        return self._pop()

    def get(self, url, headers=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        return self._pop()


def _patched_client(fake: _FakeFalClient):
    return patch(
        "src.providers.image_gen._fal_queue_base.httpx.Client",
        return_value=fake,
    )


def _make_restorer(**overrides) -> FalGfpganRestorer:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/gfpgan",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalGfpganRestorer(**defaults)


def test_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalGfpganRestorer(api_key="")


def test_body_shape_is_single_image_url():
    r = _make_restorer()
    body = r._build_body(reference_image=_jpeg_bytes())
    assert isinstance(body["image_url"], str)
    assert body["image_url"].startswith("data:image/jpeg;base64,")
    assert body.get("sync_mode") is True
    # GFPGAN has no prompt / seed / image_size knobs.
    for forbidden in ("prompt", "seed", "image_size", "image_urls"):
        assert forbidden not in body


@pytest.mark.asyncio
async def test_restore_happy_path_inline_data_uri():
    out_jpeg = _jpeg_bytes((20, 30, 40), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()
    status_url = "https://queue.fal.run/fal-ai/gfpgan/requests/r/status"
    response_url = "https://queue.fal.run/fal-ai/gfpgan/requests/r"
    responses = [
        _json_response({
            "request_id": "r",
            "status": "IN_QUEUE",
            "status_url": status_url,
            "response_url": response_url,
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "image": {"url": data_uri, "content_type": "image/jpeg"},
            "has_nsfw_concepts": [False],
        }),
    ]
    fake = _FakeFalClient(responses)

    restorer = _make_restorer()
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        out = await restorer.restore(_jpeg_bytes())

    assert out == out_jpeg
    assert fake.calls[0]["url"] == "https://queue.fal.run/fal-ai/gfpgan"
    assert fake.calls[0]["json"]["sync_mode"] is True


@pytest.mark.asyncio
async def test_restore_raises_on_nsfw():
    responses = [
        _json_response({
            "request_id": "r",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/fal-ai/gfpgan/requests/r/status",
            "response_url": "https://queue.fal.run/fal-ai/gfpgan/requests/r",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "image": {"url": "data:image/jpeg;base64,QUJD"},
            "has_nsfw_concepts": [True],
        }),
    ]
    fake = _FakeFalClient(responses)
    restorer = _make_restorer()
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        with pytest.raises(FalContentViolationError):
            await restorer.restore(_jpeg_bytes())


@pytest.mark.asyncio
async def test_restore_4xx_on_submit_no_retry():
    fake = _FakeFalClient([_error_response(400, "bad")])
    restorer = _make_restorer(max_retries=3)
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="http=400"):
            await restorer.restore(_jpeg_bytes())
    assert len(fake.calls) == 1
