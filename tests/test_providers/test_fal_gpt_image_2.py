"""Unit tests for :class:`FalGptImage2Edit` (v1.21 A/B path).

Focus areas that differ from the other FAL providers:

- GPT Image 2 forwards ``quality`` verbatim on the wire (low/medium/high)
- ``image_size`` is a ``{width, height}`` square per quality tier
  (low=1024, medium=1536, high=2048) — both dims must be multiples of 16
- ``num_images`` is pinned to 1
- no ``seed`` support on the GPT Image 2 schema — we must NOT leak one
- optional ``mask_url`` passes through when a caller provides it
- reference-image is mandatory (image-to-image only)
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from src.providers.image_gen._fal_queue_base import FalContentViolationError
from src.providers.image_gen.fal_gpt_image_2 import (
    FalGptImage2Edit,
    _QUALITY_TO_LONG_EDGE,
    _long_edge_for_quality,
)


def _jpeg_bytes(color=(100, 100, 100), size: int = 16) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _json_response(payload: dict, status: int = 200) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = {
        "content-type": "application/json",
        "x-fal-request-id": "gpt2-test-req",
    }
    body = json.dumps(payload).encode("utf-8")
    r.content = body
    r.text = body.decode("utf-8")
    r.json = MagicMock(return_value=payload)
    return r


def _error_response(
    status: int, message: str = "bad", retry_after: str | None = None,
) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    hdrs = {
        "content-type": "application/json",
        "x-fal-request-id": "gpt2-err-req",
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


def _make_gen(**overrides) -> FalGptImage2Edit:
    defaults = dict(
        api_key="uuid:secret",
        model="openai/gpt-image-2/edit",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalGptImage2Edit(**defaults)


# ----------------------------------------------------------------------
# Quality tier helper
# ----------------------------------------------------------------------


def test_quality_tier_mapping():
    assert _QUALITY_TO_LONG_EDGE == {
        "low": 1024,
        "medium": 1536,
        "high": 2048,
    }


def test_quality_tier_multiples_of_16():
    # The GPT Image 2 schema requires both dimensions to be multiples of
    # 16; if this ever drifts the API returns HTTP 422.
    for edge in _QUALITY_TO_LONG_EDGE.values():
        assert edge % 16 == 0


def test_long_edge_unknown_collapses_to_medium():
    assert _long_edge_for_quality("banana") == 1536
    assert _long_edge_for_quality(None) == 1536


# ----------------------------------------------------------------------
# Body building
# ----------------------------------------------------------------------


def test_body_has_expected_gpt_image_2_shape():
    gen = _make_gen()
    body = gen._build_body("edit", _jpeg_bytes(), {"quality": "low"})

    assert body["prompt"] == "edit"
    assert isinstance(body["image_urls"], list)
    assert len(body["image_urls"]) == 1
    assert body["image_urls"][0].startswith("data:image/jpeg;base64,")
    assert body["quality"] == "low"
    assert body["num_images"] == 1
    assert body["output_format"] in ("jpeg", "png", "webp")
    assert body["image_size"] == {"width": 1024, "height": 1024}
    # GPT Image 2 does not accept ``seed`` — make sure we never send one.
    assert "seed" not in body


def test_body_quality_medium_1536_square():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), {"quality": "medium"})
    assert body["image_size"] == {"width": 1536, "height": 1536}
    assert body["quality"] == "medium"


def test_body_quality_high_2048_square():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), {"quality": "high"})
    assert body["image_size"] == {"width": 2048, "height": 2048}
    assert body["quality"] == "high"


def test_body_unknown_quality_collapses_to_default():
    gen = _make_gen(default_quality="medium")
    body = gen._build_body("x", _jpeg_bytes(), {"quality": "ultra"})
    assert body["quality"] == "medium"
    assert body["image_size"] == {"width": 1536, "height": 1536}


def test_body_missing_quality_uses_default():
    gen = _make_gen(default_quality="high")
    body = gen._build_body("x", _jpeg_bytes(), None)
    assert body["quality"] == "high"
    assert body["image_size"] == {"width": 2048, "height": 2048}


def test_body_forwards_mask_url_when_present():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"quality": "medium", "mask_url": "https://example.com/mask.png"},
    )
    assert body["mask_url"] == "https://example.com/mask.png"


def test_body_ignores_non_string_mask_url():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(), {"quality": "medium", "mask_url": 12345},
    )
    assert "mask_url" not in body


def test_body_rejects_missing_reference():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        gen._build_body("x", b"", None)


def test_constructor_rejects_empty_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalGptImage2Edit(api_key="")


def test_constructor_clamps_unknown_default_quality():
    gen = _make_gen(default_quality="banana")
    assert gen._default_quality == "medium"


def test_constructor_accepts_webp_output_format():
    gen = _make_gen(output_format="webp")
    assert gen._output_format == "webp"


# ----------------------------------------------------------------------
# Happy path — async generate end-to-end
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_inline_data_uri():
    import base64
    out_jpeg = _jpeg_bytes((10, 20, 30), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()

    responses = [
        _json_response({
            "request_id": "r",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/openai/gpt-image-2/requests/r/status",
            "response_url": "https://queue.fal.run/openai/gpt-image-2/requests/r",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": data_uri, "content_type": "image/jpeg"}],
            "has_nsfw_concepts": [False],
        }),
    ]
    fake = _FakeFalClient(responses)

    gen = _make_gen()
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        result = await gen.generate(
            "portrait",
            reference_image=_jpeg_bytes(),
            params={"quality": "medium"},
        )

    assert result == out_jpeg
    submit = fake.calls[0]
    assert submit["method"] == "POST"
    assert submit["url"].endswith("/openai/gpt-image-2/edit")
    assert submit["json"]["quality"] == "medium"
    assert submit["json"]["image_size"] == {"width": 1536, "height": 1536}


@pytest.mark.asyncio
async def test_generate_requires_reference_image():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        await gen.generate("x", reference_image=None)


@pytest.mark.asyncio
async def test_4xx_on_submit_no_retry():
    fake = _FakeFalClient([_error_response(422, message="bad image_size")])
    gen = _make_gen(max_retries=3)
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="http=422"):
            await gen.generate("p", reference_image=_jpeg_bytes())
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_nsfw_no_retry():
    responses = [
        _json_response({
            "request_id": "nsfw",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/openai/gpt-image-2/requests/nsfw/status",
            "response_url": "https://queue.fal.run/openai/gpt-image-2/requests/nsfw",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": "data:image/jpeg;base64,AAAA"}],
            "has_nsfw_concepts": [True],
        }),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=3)
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        with pytest.raises(FalContentViolationError):
            await gen.generate("p", reference_image=_jpeg_bytes())
