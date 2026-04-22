"""Reve /v1/image/edit body allowlist regression tests.

Reve REST ``/v1/image/edit`` rejects any body field other than
``edit_instruction``, ``reference_image`` and ``version`` with
``INVALID_PARAMETER_VALUE``. The prior pipeline leaked
``aspect_ratio``, ``test_time_scaling``, ``postprocessing``,
``mask_image``, ``mask_region`` and ``use_edit`` onto the wire and
broke every edit call after the 2026-04-21 regression. These tests
lock the fix in. /create and /remix branches have been retired; see
docs/architecture/reserved.md.
"""
from __future__ import annotations

from src.providers.image_gen.reve_provider import ReveImageGen


_FORBIDDEN = (
    "test_time_scaling",
    "postprocessing",
    "mask_image",
    "mask_region",
    "use_edit",
)


def _client() -> ReveImageGen:
    return ReveImageGen(
        api_token="papi.test",
        api_host="https://api.reve.com",
        version="latest",
    )


def test_edit_body_is_whitelisted():
    client = _client()
    body = client._build_body(
        prompt="Change background to studio.",
        reference_image=b"\x89PNG\r\n\x1a\n",
        params={
            "aspect_ratio": "3:4",
            "test_time_scaling": 3,
            "postprocessing": [{"process": "upscale", "upscale_factor": 2}],
            "mask_region": "background",
            "mask_image": b"ignored",
            "use_edit": True,
            "version": "latest",
        },
    )
    assert set(body.keys()) <= {"edit_instruction", "reference_image", "version"}
    assert "edit_instruction" in body
    assert "reference_image" in body
    for key in _FORBIDDEN + ("aspect_ratio", "prompt", "reference_images"):
        assert key not in body, f"forbidden key {key!r} leaked into edit body"


def test_edit_body_omits_aspect_ratio_by_default():
    """aspect_ratio is NOT accepted by /v1/image/edit — must never appear."""
    client = _client()
    body = client._build_body(
        prompt="edit",
        reference_image=b"x",
        params=None,
    )
    assert "aspect_ratio" not in body


def test_edit_endpoint_has_no_trailing_slash():
    client = _client()
    assert client.API_EDIT == "/v1/image/edit"


def test_build_body_requires_reference_image():
    import pytest

    client = _client()
    with pytest.raises(ValueError):
        client._build_body(prompt="p", reference_image=b"", params=None)
