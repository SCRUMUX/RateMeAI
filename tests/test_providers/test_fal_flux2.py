"""Unit tests for :class:`FalFlux2ImageGen` (FLUX.2 Pro Edit).

The wire protocol (queue submit → status poll → result fetch → decode)
is identical to the Kontext provider covered by ``test_fal_flux.py``,
so these tests focus on the bits that actually differ:

- ``image_urls`` is a **list**, even for a single reference
- ``image_size`` accepts a preset enum OR a ``{width, height}`` dict
- no ``guidance_scale`` / ``enhance_prompt`` keys on the wire
- random seed default (no caller-provided seed) still lands on the body
- data-URI decode path mirrors Kontext
- 429 / 5xx / NSFW behave the same (retry / retry / no-retry)
"""
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
    FalContentViolationError,
)
from src.providers.image_gen.fal_flux2 import FalFlux2ImageGen


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
        "x-fal-request-id": "fal2-test-req",
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
        "x-fal-request-id": "fal2-err-req",
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
    """httpx.Client double that returns queued responses in order."""

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
        self.calls.append({
            "method": "GET", "url": url, "headers": headers,
        })
        return self._pop()


def _patched_client(fake: _FakeFalClient):
    return patch(
        "src.providers.image_gen._fal_queue_base.httpx.Client",
        return_value=fake,
    )


def _make_gen(**overrides) -> FalFlux2ImageGen:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/flux-2-pro/edit",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalFlux2ImageGen(**defaults)


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------


def test_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalFlux2ImageGen(api_key="")


def test_unknown_safety_tolerance_is_clamped():
    gen = _make_gen(safety_tolerance="9")
    assert gen._safety_tolerance == "2"


# ----------------------------------------------------------------------
# Body building — FLUX.2 Pro Edit shape
# ----------------------------------------------------------------------


def test_body_uses_image_urls_list_and_no_kontext_fields():
    gen = _make_gen()
    ref = _jpeg_bytes()
    body = gen._build_body("put a hat on them", ref, {"seed": 42})

    # image_urls is a list, even with one reference.
    assert isinstance(body["image_urls"], list)
    assert len(body["image_urls"]) == 1
    assert body["image_urls"][0].startswith("data:image/jpeg;base64,")
    assert base64.b64encode(ref).decode("ascii") in body["image_urls"][0]

    # Kontext-era keys must NOT appear.
    for forbidden in ("image_url", "guidance_scale", "enhance_prompt"):
        assert forbidden not in body

    assert body["prompt"] == "put a hat on them"
    assert body["sync_mode"] is True
    assert body["num_images"] == 1
    assert body["seed"] == 42


def test_body_rejects_missing_reference():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        gen._build_body("x", b"", None)


def test_body_default_image_size_is_portrait_4_3():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), None)
    assert body["image_size"] == "portrait_4_3"


def test_body_accepts_preset_image_size():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(), {"image_size": "portrait_16_9"},
    )
    assert body["image_size"] == "portrait_16_9"


def test_body_accepts_custom_image_size_dict():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(), {"image_size": {"width": 1280, "height": 1600}},
    )
    assert body["image_size"] == {"width": 1280, "height": 1600}


def test_body_rejects_malformed_custom_size_falling_back_to_default():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"image_size": {"width": "oops", "height": None}},
    )
    # Malformed → provider resolves default (portrait_4_3 string preset).
    assert body["image_size"] == "portrait_4_3"


def test_body_rejects_unknown_preset_falling_back_to_default():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(), {"image_size": "vertical_banana"},
    )
    assert body["image_size"] == "portrait_4_3"


def test_body_seed_default_is_random_positive_int():
    gen = _make_gen()
    bodies = [gen._build_body("x", _jpeg_bytes(), None) for _ in range(3)]
    seeds = [b["seed"] for b in bodies]
    for s in seeds:
        assert isinstance(s, int)
        assert 1 <= s < 2**31
    # Statistically extremely unlikely to all collide.
    assert len(set(seeds)) > 1


# ----------------------------------------------------------------------
# Happy path — full sync flow
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_inline_data_uri():
    out_jpeg = _jpeg_bytes((10, 20, 30), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()

    status_url = "https://queue.fal.run/fal-ai/flux-2-pro/requests/r/status"
    response_url = "https://queue.fal.run/fal-ai/flux-2-pro/requests/r"
    responses = [
        _json_response({
            "request_id": "r",
            "status": "IN_QUEUE",
            "status_url": status_url,
            "response_url": response_url,
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": data_uri, "content_type": "image/jpeg"}],
            "has_nsfw_concepts": [False],
            "seed": 999,
            "prompt": "edit",
        }),
    ]
    fake = _FakeFalClient(responses)

    gen = _make_gen()
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        result = await gen.generate(
            "headshot on studio backdrop",
            reference_image=_jpeg_bytes(),
            params={"image_size": {"width": 1280, "height": 1600}},
        )

    assert result == out_jpeg
    assert len(fake.calls) == 3
    submit, status_poll, fetch = fake.calls
    assert submit["method"] == "POST"
    assert submit["url"] == "https://queue.fal.run/fal-ai/flux-2-pro/edit"
    assert submit["headers"]["Authorization"].startswith("Key ")
    assert submit["json"]["sync_mode"] is True
    assert submit["json"]["image_size"] == {"width": 1280, "height": 1600}
    assert isinstance(submit["json"]["image_urls"], list)
    assert status_poll["method"] == "GET"
    assert status_poll["url"] == status_url
    assert fetch["method"] == "GET"
    assert fetch["url"] == response_url


@pytest.mark.asyncio
async def test_generate_fetches_external_image_url_when_not_data_uri():
    out_jpeg = _jpeg_bytes((50, 50, 50), size=24)
    image_url = "https://fal.media/files/abc/out.jpg"

    responses = [
        _json_response({
            "request_id": "x",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/x/status",
            "response_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/x",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": image_url}],
            "has_nsfw_concepts": [False],
        }),
        _binary_response(out_jpeg),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen()

    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        result = await gen.generate("p", reference_image=_jpeg_bytes())

    assert result == out_jpeg
    assert fake.calls[-1]["url"] == image_url


# ----------------------------------------------------------------------
# Errors
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
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="http=400"):
            await gen.generate("p", reference_image=_jpeg_bytes())
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_429_is_retried():
    out_jpeg = _jpeg_bytes((0, 0, 0))
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()
    responses = [
        _error_response(429, message="slow down", retry_after="0"),
        _json_response({
            "request_id": "ok",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/ok/status",
            "response_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/ok",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": data_uri}],
            "has_nsfw_concepts": [False],
        }),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=3)
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        result = await gen.generate("p", reference_image=_jpeg_bytes())
    assert result == out_jpeg


@pytest.mark.asyncio
async def test_5xx_is_retried_then_succeeds():
    out_jpeg = _jpeg_bytes((0, 0, 0))
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()
    responses = [
        _error_response(502, message="upstream"),
        _json_response({
            "request_id": "ok",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/ok/status",
            "response_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/ok",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({
            "images": [{"url": data_uri}],
            "has_nsfw_concepts": [False],
        }),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=2)
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        result = await gen.generate("p", reference_image=_jpeg_bytes())
    assert result == out_jpeg


@pytest.mark.asyncio
async def test_nsfw_no_retry():
    responses = [
        _json_response({
            "request_id": "nsfw",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/nsfw/status",
            "response_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/nsfw",
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
    submits = [c for c in fake.calls if c["method"] == "POST"]
    assert len(submits) == 1


@pytest.mark.asyncio
async def test_missing_images_raises():
    responses = [
        _json_response({
            "request_id": "e",
            "status": "IN_QUEUE",
            "status_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/e/status",
            "response_url": "https://queue.fal.run/fal-ai/flux-2-pro/requests/e",
        }),
        _json_response({"status": "COMPLETED"}),
        _json_response({"images": [], "has_nsfw_concepts": []}),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=1)
    with _patched_client(fake), patch(
        "src.providers.image_gen._fal_queue_base.time.sleep"
    ):
        with pytest.raises(RuntimeError, match="no images"):
            await gen.generate("p", reference_image=_jpeg_bytes())


def test_submit_missing_request_id_raises():
    gen = _make_gen()
    resp = _json_response({"status": "IN_QUEUE"})
    resp.headers = {"content-type": "application/json"}
    fake = _FakeFalClient([resp])
    with pytest.raises(FalAPIError, match="request_id"):
        gen._submit(fake, {"prompt": "x"})
