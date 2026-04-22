"""Unit tests for :class:`FalPuLIDImageGen` (fal-ai/pulid).

Focus: the PuLID-specific body shape — ``reference_images`` list,
``id_scale`` / ``pulid_mode`` handling, clamping of out-of-range
numerics, and the "no reference → error" invariant. The wire protocol
(queue submit / poll / fetch) is already covered by the shared FAL
queue tests via :class:`FalQueueClient`.
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from src.providers.image_gen.fal_pulid import FalPuLIDImageGen


def _jpeg_bytes(color=(120, 180, 210), size: int = 32) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_gen(**overrides) -> FalPuLIDImageGen:
    defaults = dict(
        api_key="uuid:secret",
        model="fal-ai/pulid",
        api_host="https://queue.fal.run",
        max_retries=1,
        request_timeout=5.0,
        poll_interval=0.01,
    )
    defaults.update(overrides)
    return FalPuLIDImageGen(**defaults)


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------


def test_requires_api_key():
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        FalPuLIDImageGen(api_key="")


def test_defaults_are_clamped_in_constructor():
    # v1.19 — widened clamps: steps [1, 50], guidance [1.0, 10.0],
    # id_scale [0.01, 5.0].
    gen = _make_gen(
        id_scale=9.0,
        num_inference_steps=200,
        guidance_scale=20.0,
        pulid_mode="not-a-real-mode",
    )
    assert gen._id_scale == 5.0
    assert gen._steps == 50
    assert gen._guidance_scale == 10.0
    assert gen._mode == "fidelity"


# ----------------------------------------------------------------------
# Body builder
# ----------------------------------------------------------------------


def test_body_uses_reference_images_list_with_face_crop():
    gen = _make_gen()
    face = _jpeg_bytes()
    body = gen._build_body("biker on golden-hour road", face, None)

    assert isinstance(body["reference_images"], list)
    assert len(body["reference_images"]) == 1
    ref = body["reference_images"][0]
    assert isinstance(ref, dict)
    assert ref["image_url"].startswith("data:image/jpeg;base64,")
    assert base64.b64encode(face).decode("ascii") in ref["image_url"]

    assert body["prompt"] == "biker on golden-hour road"
    assert body["num_images"] == 1
    assert body["mode"] in ("fidelity", "extreme style")


def test_body_rejects_missing_reference():
    gen = _make_gen()
    with pytest.raises(ValueError, match="reference_image"):
        gen._build_body("x", b"", None)


def test_body_honours_retry_params_from_executor():
    # v1.19 retry path: executor escalates id_scale / steps / guidance
    # on identity_match failures, and stays on mode=fidelity (NOT
    # extreme style, which actually weakens identity).
    gen = _make_gen(pulid_mode="fidelity", id_scale=0.5)
    body = gen._build_body(
        "retry prompt",
        _jpeg_bytes(),
        {"pulid_mode": "fidelity", "id_scale": 1.2,
         "num_inference_steps": 35, "guidance_scale": 5.0},
    )
    assert body["mode"] == "fidelity"
    assert body["id_scale"] == 1.2
    assert body["num_inference_steps"] == 35
    assert body["guidance_scale"] == 5.0


def test_body_clamps_out_of_range_id_scale():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"id_scale": 99.0},
    )
    assert body["id_scale"] == 5.0


def test_body_clamps_steps_and_guidance():
    # v1.19 widened clamps: steps [1, 50], guidance [1.0, 10.0].
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"num_inference_steps": 200, "guidance_scale": 25.0},
    )
    assert body["num_inference_steps"] == 50
    assert body["guidance_scale"] == 10.0


def test_body_ships_negative_prompt_by_default():
    # v1.19: the body builder bakes a default negative_prompt covering
    # the duplicate-subject / deformed-hands failure modes that were
    # endemic to v1.18. The prompt must be non-empty and mention the
    # two key concepts we want to suppress.
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), None)
    neg = body["negative_prompt"]
    assert isinstance(neg, str) and neg
    assert "two people" in neg
    assert "duplicate" in neg or "twins" in neg


def test_body_honours_custom_negative_prompt():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"negative_prompt": "custom negative override"},
    )
    assert body["negative_prompt"] == "custom negative override"


def test_body_ships_max_sequence_length_512_by_default():
    # v1.19: default 512 so the full 1200-char builder reaches the
    # sampler instead of being truncated at ~500 chars by the API
    # default (128).
    gen = _make_gen()
    body = gen._build_body("x", _jpeg_bytes(), None)
    assert body["max_sequence_length"] == 512


def test_body_max_sequence_length_falls_back_to_512_on_invalid():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(), {"max_sequence_length": 1024},
    )
    assert body["max_sequence_length"] == 512


def test_body_seed_default_is_random_int():
    gen = _make_gen()
    bodies = [
        gen._build_body("x", _jpeg_bytes(), None) for _ in range(3)
    ]
    seeds = {b["seed"] for b in bodies}
    assert all(isinstance(s, int) and 1 <= s < 2**31 for s in seeds)
    assert len(seeds) > 1


def test_body_accepts_custom_image_size_dict():
    gen = _make_gen()
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"image_size": {"width": 1024, "height": 1536}},
    )
    assert body["image_size"] == {"width": 1024, "height": 1536}


def test_body_rejects_unknown_preset_falls_back_to_default():
    gen = _make_gen(default_image_size="portrait_4_3")
    body = gen._build_body(
        "x", _jpeg_bytes(), {"image_size": "vertical_banana"},
    )
    assert body["image_size"] == "portrait_4_3"


def test_body_accepts_extra_reference_faces():
    gen = _make_gen()
    extra_face = _jpeg_bytes(color=(50, 60, 70))
    body = gen._build_body(
        "x", _jpeg_bytes(),
        {"extra_reference_faces": [extra_face]},
    )
    assert len(body["reference_images"]) == 2
    assert body["reference_images"][1]["image_url"].startswith(
        "data:image/jpeg;base64,"
    )
