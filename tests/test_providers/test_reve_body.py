"""Reve request-body allowlist regression tests (v1.13.3).

Reve REST ``/v1/image/edit`` rejects any body field other than
``edit_instruction``, ``reference_image`` and ``version`` with
``INVALID_PARAMETER_VALUE``. The same holds for ``create`` and
``remix`` — each endpoint has a strict allowlist. The prior pipeline
leaked ``aspect_ratio``, ``test_time_scaling``, ``postprocessing``,
``mask_image``, ``mask_region`` and ``use_edit`` onto the wire and
broke every edit call after the 2026-04-21 regression. These tests
lock the fix in.
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
        aspect_ratio="3:4",
        version="latest",
    )


def test_edit_body_is_whitelisted():
    client = _client()
    body = client._build_body(
        client.API_EDIT,
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


def test_create_body_is_whitelisted():
    client = _client()
    body = client._build_body(
        client.API_CREATE,
        prompt="A scenic beach.",
        reference_image=None,
        params={
            "test_time_scaling": 3,
            "postprocessing": [{"process": "upscale"}],
            "mask_region": "background",
            "use_edit": True,
            "aspect_ratio": "16:9",
            "version": "latest",
        },
    )
    assert set(body.keys()) <= {"prompt", "aspect_ratio", "version"}
    assert body["prompt"] == "A scenic beach."
    for key in _FORBIDDEN + ("edit_instruction", "reference_image", "reference_images"):
        assert key not in body, f"forbidden key {key!r} leaked into create body"


def test_remix_body_is_whitelisted():
    client = _client()
    body = client._build_body(
        client.API_REMIX,
        prompt="Remix this photo.",
        reference_image=b"\x89PNG\r\n\x1a\n",
        params={
            "test_time_scaling": 4,
            "postprocessing": [{"process": "upscale"}],
            "mask_region": "clothing",
            "use_edit": True,
            "aspect_ratio": "1:1",
            "version": "latest",
        },
    )
    assert set(body.keys()) <= {"prompt", "reference_images", "aspect_ratio", "version"}
    assert body["prompt"] == "Remix this photo."
    assert isinstance(body["reference_images"], list) and len(body["reference_images"]) == 1
    for key in _FORBIDDEN + ("edit_instruction", "reference_image"):
        assert key not in body, f"forbidden key {key!r} leaked into remix body"


def test_edit_body_omits_aspect_ratio_by_default():
    """aspect_ratio is NOT accepted by /v1/image/edit — must never appear."""
    client = _client()
    body = client._build_body(
        client.API_EDIT,
        prompt="edit",
        reference_image=b"x",
        params=None,
    )
    assert "aspect_ratio" not in body


def test_endpoints_have_no_trailing_slash():
    client = _client()
    assert client.API_CREATE == "/v1/image/create"
    assert client.API_EDIT == "/v1/image/edit"
    assert client.API_REMIX == "/v1/image/remix"


def test_create_body_skips_auto_aspect_ratio():
    """'auto' is an executor-level sentinel, not a Reve value."""
    client = ReveImageGen(
        api_token="papi.x",
        api_host="https://api.reve.com",
        aspect_ratio="auto",
    )
    body = client._build_body(
        client.API_CREATE,
        prompt="p",
        reference_image=None,
        params={"aspect_ratio": "auto"},
    )
    assert "aspect_ratio" not in body
