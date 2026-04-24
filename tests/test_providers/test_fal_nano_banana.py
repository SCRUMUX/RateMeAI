"""Unit tests for :class:`FalNanoBanana2Edit` (v1.21 A/B path).

The wire protocol (queue submit → status poll → result fetch → decode)
is identical to every other FAL queue provider (PuLID / FLUX / Seedream
/ FLUX.2); it lives in :mod:`_fal_queue_base` and is already covered by
those provider-specific tests. These tests focus on the bits that
actually differ for Nano Banana 2 Edit:

- ``image_urls`` is a list (single reference)
- ``resolution`` is an enum (``1K``/``2K``/``4K``, v1.22 floor raised
  from ``0.5K``) keyed off the quality tier (``low``/``medium``/``high``)
  and ``aspect_ratio`` defaults to ``"auto"`` (Nano Banana 2 Edit has
  no ``image_size`` field)
- ``num_images`` is pinned to 1 so cost accounting stays 1-call = 1-image
- missing / unknown ``quality`` collapses to ``default_quality``
- reference-image is mandatory (image-to-image only)
"""

from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from src.providers.image_gen._fal_queue_base import (
    FalAPIError,
    FalContentViolationError,
)
from src.providers.image_gen.fal_nano_banana import (
    FalNanoBanana2Edit,
    _QUALITY_TO_RESOLUTION,
    _resolution_for_quality,
    _thinking_level_for_quality,
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
        "x-fal-request-id": "nb-test-req",
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
        "x-fal-request-id": "nb-err-req",
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


def _make_gen(**overrides) -> FalNanoBanana2Edit:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/nano-banana-2/edit",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalNanoBanana2Edit(**defaults)


# ----------------------------------------------------------------------
# Quality tier helper
# ----------------------------------------------------------------------


def test_quality_tier_mapping():
    # v1.22: floor lifted from 0.5K → 1K so the cheapest user-visible
    # output is still ~1 MP (512px portraits were below prod quality).
    # v1.24: 4K dropped; ``high`` is now 2K + thinking=high.
    assert _QUALITY_TO_RESOLUTION == {"low": "1K", "medium": "2K", "high": "2K"}
    assert _resolution_for_quality("low") == "1K"
    assert _resolution_for_quality("medium") == "2K"
    assert _resolution_for_quality("high") == "2K"


def test_quality_tier_unknown_falls_back_to_medium():
    assert _resolution_for_quality("ultra") == "2K"
    assert _resolution_for_quality(None) == "2K"
    assert _resolution_for_quality("") == "2K"


# ----------------------------------------------------------------------
# Body building
# ----------------------------------------------------------------------


def test_body_has_expected_nano_banana_shape():
    gen = _make_gen()
    ref = _jpeg_bytes()
    body = gen._build_body("edit me", ref, {"quality": "low", "seed": 7})

    assert body["prompt"] == "edit me"
    assert isinstance(body["image_urls"], list)
    assert len(body["image_urls"]) == 1
    assert body["image_urls"][0].startswith("data:image/jpeg;base64,")
    assert body["num_images"] == 1
    assert body["output_format"] in ("jpeg", "png")
    # v1.22: low tier now maps to 1K (was 0.5K).
    assert body["resolution"] == "1K"
    assert body["aspect_ratio"] == "auto"
    # v1.23: reproducibility pins.
    assert body["safety_tolerance"] == "4"
    assert body["limit_generations"] is True
    # v1.23: low keeps fast non-reasoning mode.
    assert "thinking_level" not in body
    assert "image_size" not in body, (
        "Nano Banana 2 Edit schema has no image_size field; sending it would 422"
    )
    assert body["seed"] == 7


def test_body_quality_medium_runs_fast_mode():
    # v1.24: medium now runs 2K without reasoning so it keeps its
    # fast latency budget; thinking is reserved for ``high``.
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), {"quality": "medium"})
    assert body["resolution"] == "2K"
    assert "thinking_level" not in body


def test_body_quality_high_enables_thinking_high():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), {"quality": "high"})
    # v1.24: resolution capped at 2K; ``high`` differs from ``medium``
    # only by ``thinking_level=high`` (reasoning-guided edit).
    assert body["resolution"] == "2K"
    assert body["thinking_level"] == "high"


def test_body_explicit_thinking_level_override_honoured():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"quality": "high", "thinking_level": "minimal"},
    )
    assert body["thinking_level"] == "minimal"


def test_body_invalid_thinking_level_falls_back_to_quality_default():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"quality": "high", "thinking_level": "garbage"},
    )
    assert body["thinking_level"] == "high"


def test_body_invalid_safety_tolerance_falls_back_to_4():
    gen = _make_gen()
    body = gen._build_body(
        "x",
        _jpeg_bytes(),
        {"quality": "low", "safety_tolerance": "99"},
    )
    assert body["safety_tolerance"] == "4"


def test_thinking_level_helper():
    # v1.24: only ``high`` opts into Gemini reasoning; medium now runs
    # fast mode so the mid-tier keeps its latency budget.
    assert _thinking_level_for_quality("low") is None
    assert _thinking_level_for_quality("medium") is None
    assert _thinking_level_for_quality("high") == "high"
    assert _thinking_level_for_quality(None) is None  # defaults to medium -> fast
    assert _thinking_level_for_quality("banana") is None


def test_body_unknown_quality_collapses_to_default_quality():
    gen = _make_gen(default_quality="medium")
    body = gen._build_body("x", _jpeg_bytes(), {"quality": "huge"})
    assert body["resolution"] == "2K"


def test_body_missing_quality_uses_default_quality():
    gen = _make_gen(default_quality="low")
    body = gen._build_body("x", _jpeg_bytes(), None)
    assert body["resolution"] == "1K"


def test_body_aspect_ratio_override_honoured():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), {"aspect_ratio": "3:4"})
    assert body["aspect_ratio"] == "3:4"


def test_body_invalid_aspect_ratio_falls_back_to_auto():
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), {"aspect_ratio": "7:3"})
    assert body["aspect_ratio"] == "auto"


def test_body_seed_default_is_random_positive_int():
    gen = _make_gen()
    seeds = {gen._build_body("x", _jpeg_bytes(), None)["seed"] for _ in range(5)}
    assert all(isinstance(s, int) and 1 <= s < 2**31 for s in seeds)
    # Collision across 5 independent SystemRandom draws is astronomically
    # unlikely — this protects against a regression where the default
    # seed is hard-coded.
    assert len(seeds) > 1


def test_body_rejects_missing_reference():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        gen._build_body("x", b"", None)


def test_constructor_rejects_empty_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalNanoBanana2Edit(api_key="")


def test_constructor_clamps_unknown_default_quality():
    gen = _make_gen(default_quality="unheard_of")
    assert gen._default_quality == "medium"


def test_constructor_clamps_unknown_output_format():
    gen = _make_gen(output_format="bmp")
    assert gen._output_format == "jpeg"


# ----------------------------------------------------------------------
# Happy path — async generate end-to-end
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_inline_data_uri():
    out_jpeg = _jpeg_bytes((10, 20, 30), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()

    responses = [
        _json_response(
            {
                "request_id": "r",
                "status": "IN_QUEUE",
                "status_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/r/status",
                "response_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/r",
            }
        ),
        _json_response({"status": "COMPLETED"}),
        _json_response(
            {
                "images": [{"url": data_uri, "content_type": "image/jpeg"}],
                "has_nsfw_concepts": [False],
                "seed": 1234,
            }
        ),
    ]
    fake = _FakeFalClient(responses)

    gen = _make_gen()
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        result = await gen.generate(
            "portrait",
            reference_image=_jpeg_bytes(),
            params={"quality": "medium"},
        )

    assert result == out_jpeg
    submit = fake.calls[0]
    assert submit["method"] == "POST"
    assert submit["url"].endswith("/fal-ai/nano-banana-2/edit")
    assert submit["headers"]["Authorization"].startswith("Key ")
    # medium quality → 2K (v1.22 mapping)
    assert submit["json"]["resolution"] == "2K"
    assert submit["json"]["aspect_ratio"] == "auto"


@pytest.mark.asyncio
async def test_generate_requires_reference_image():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        await gen.generate("x", reference_image=None)


# ----------------------------------------------------------------------
# Error paths — reuse of _fal_queue_base machinery
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_4xx_on_submit_no_retry():
    fake = _FakeFalClient([_error_response(400, message="bad prompt")])
    gen = _make_gen(max_retries=3)
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
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
        _json_response(
            {
                "request_id": "ok",
                "status": "IN_QUEUE",
                "status_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/ok/status",
                "response_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/ok",
            }
        ),
        _json_response({"status": "COMPLETED"}),
        _json_response(
            {
                "images": [{"url": data_uri}],
                "has_nsfw_concepts": [False],
            }
        ),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=3)
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        result = await gen.generate("p", reference_image=_jpeg_bytes())
    assert result == out_jpeg


@pytest.mark.asyncio
async def test_nsfw_no_retry():
    responses = [
        _json_response(
            {
                "request_id": "nsfw",
                "status": "IN_QUEUE",
                "status_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/nsfw/status",
                "response_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/nsfw",
            }
        ),
        _json_response({"status": "COMPLETED"}),
        _json_response(
            {
                "images": [{"url": "data:image/jpeg;base64,AAAA"}],
                "has_nsfw_concepts": [True],
            }
        ),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen(max_retries=3)
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        with pytest.raises(FalContentViolationError):
            await gen.generate("p", reference_image=_jpeg_bytes())
    submits = [c for c in fake.calls if c["method"] == "POST"]
    assert len(submits) == 1


def test_submit_missing_request_id_raises():
    gen = _make_gen()
    resp = _json_response({"status": "IN_QUEUE"})
    resp.headers = {"content-type": "application/json"}
    fake = _FakeFalClient([resp])
    with pytest.raises(FalAPIError, match="request_id"):
        gen._submit(fake, {"prompt": "x"})


# ----------------------------------------------------------------------
# v1.24.2 regression — FAL submit response without explicit
# ``status_url`` / ``response_url``. Falls back to URL synthesis, which
# must keep the full ``fal-ai/nano-banana-2/edit`` appId (previously the
# ``/edit`` suffix was dropped → 404 on status poll).
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_without_status_url_uses_full_app_path():
    out_jpeg = _jpeg_bytes((10, 20, 30), size=32)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(out_jpeg).decode()

    # Submit response without status_url/response_url → forces fallback
    # URL synthesis in _fal_queue_base.
    responses = [
        _json_response(
            {
                "request_id": "req-abc",
                "status": "IN_QUEUE",
            }
        ),
        _json_response({"status": "COMPLETED"}),
        _json_response(
            {
                "images": [{"url": data_uri, "content_type": "image/jpeg"}],
                "has_nsfw_concepts": [False],
                "seed": 42,
            }
        ),
    ]
    fake = _FakeFalClient(responses)
    gen = _make_gen()
    with (
        _patched_client(fake),
        patch("src.providers.image_gen._fal_queue_base.time.sleep"),
    ):
        result = await gen.generate(
            "p", reference_image=_jpeg_bytes(), params={"quality": "low"}
        )

    assert result == out_jpeg
    gets = [c for c in fake.calls if c["method"] == "GET"]
    # status poll + result fetch both go through the fallback synthesiser;
    # both must use the *full* appId with the ``/edit`` subpath.
    assert len(gets) == 2
    status_url = gets[0]["url"]
    result_url = gets[1]["url"]
    assert status_url == (
        "https://queue.fal.run/fal-ai/nano-banana-2/edit/requests/req-abc/status"
    ), f"status URL must include /edit subpath, got {status_url!r}"
    assert result_url == (
        "https://queue.fal.run/fal-ai/nano-banana-2/edit/requests/req-abc"
    ), f"result URL must include /edit subpath, got {result_url!r}"
