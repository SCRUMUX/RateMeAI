"""Unit tests for :class:`StyleRouter` — the hybrid image-gen delegator.

Verifies:

1. ``identity_scene`` routes to PuLID with the face crop as reference.
2. ``scene_preserve`` routes to Seedream with the full photo as reference.
3. Missing/unknown mode routes to the fallback provider.
4. PuLID path gracefully degrades to ``scene_preserve`` when the face
   crop fails (no face) and records the expected metric overrides.
5. ``generation_mode`` is stripped from params before being forwarded.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.providers.image_gen.style_router import StyleRouter
from src.services.face_crop import FaceCropReason, FaceCropResult


class _Backend:
    """Minimal awaitable ImageGenProvider double for the router tests."""

    def __init__(self, name: str, output: bytes = b"dummy-jpeg-bytes"):
        self.name = name
        self.output = output
        self.generate = AsyncMock(side_effect=self._record)
        self.seen: list[dict] = []

    async def _record(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        self.seen.append({
            "prompt": prompt,
            "ref_len": len(reference_image or b""),
            "params": dict(params or {}),
        })
        return self.output

    async def close(self) -> None:
        pass


def _make_router(**overrides) -> tuple[StyleRouter, _Backend, _Backend, _Backend]:
    pulid = _Backend("pulid", output=b"pulid-out")
    seedream = _Backend("seedream", output=b"seedream-out")
    fallback = _Backend("fallback", output=b"fallback-out")
    defaults = dict(pulid=pulid, seedream=seedream, fallback=fallback)
    defaults.update(overrides)
    return StyleRouter(**defaults), pulid, seedream, fallback


@pytest.mark.asyncio
async def test_identity_scene_routes_to_pulid_with_face_crop():
    router, pulid, seedream, fallback = _make_router()
    crop_ok = FaceCropResult(
        image_bytes=b"FACE-CROP-JPEG", reason=FaceCropReason.OK,
    )
    with patch(
        "src.providers.image_gen.style_router.crop_face_for_pulid",
        return_value=crop_ok,
    ):
        out = await router.generate(
            "biker at sunset",
            reference_image=b"full-photo-bytes-" * 10,
            params={"generation_mode": "identity_scene"},
        )

    assert out == b"pulid-out"
    assert len(pulid.seen) == 1
    call = pulid.seen[0]
    assert call["prompt"] == "biker at sunset"
    assert call["ref_len"] == len(b"FACE-CROP-JPEG")
    assert "generation_mode" not in call["params"]
    assert len(seedream.seen) == 0
    assert len(fallback.seen) == 0


@pytest.mark.asyncio
async def test_scene_preserve_routes_to_seedream_with_full_photo():
    router, pulid, seedream, fallback = _make_router()
    full_photo = b"full-photo-bytes" * 10

    out = await router.generate(
        "preserve the coffee shop",
        reference_image=full_photo,
        params={"generation_mode": "scene_preserve"},
    )

    assert out == b"seedream-out"
    assert len(seedream.seen) == 1
    call = seedream.seen[0]
    assert call["ref_len"] == len(full_photo)
    assert "generation_mode" not in call["params"]
    assert len(pulid.seen) == 0
    assert len(fallback.seen) == 0


@pytest.mark.asyncio
async def test_missing_mode_defaults_to_identity_scene_then_pulid():
    """Missing mode → identity_scene default; face crop OK → PuLID."""
    router, pulid, seedream, fallback = _make_router()
    crop_ok = FaceCropResult(
        image_bytes=b"FACE", reason=FaceCropReason.OK,
    )
    with patch(
        "src.providers.image_gen.style_router.crop_face_for_pulid",
        return_value=crop_ok,
    ):
        await router.generate(
            "prompt",
            reference_image=b"photo",
            params={},
        )
    assert len(pulid.seen) == 1
    assert len(seedream.seen) == 0


@pytest.mark.asyncio
async def test_face_crop_failure_falls_back_to_scene_preserve():
    router, pulid, seedream, fallback = _make_router()
    crop_fail = FaceCropResult(
        image_bytes=None, reason=FaceCropReason.NO_FACE,
    )
    with patch(
        "src.providers.image_gen.style_router.crop_face_for_pulid",
        return_value=crop_fail,
    ):
        out = await router.generate(
            "prompt",
            reference_image=b"photo-without-a-face",
            params={"generation_mode": "identity_scene"},
        )
    assert out == b"seedream-out"
    assert len(pulid.seen) == 0
    assert len(seedream.seen) == 1


@pytest.mark.asyncio
async def test_identity_scene_without_pulid_provider_uses_fallback():
    """If PuLID isn't wired, identity_scene flows through fallback."""
    router, pulid, seedream, fallback = _make_router(pulid=None)
    out = await router.generate(
        "prompt",
        reference_image=b"photo",
        params={"generation_mode": "identity_scene"},
    )
    assert out == b"fallback-out"
    assert len(fallback.seen) == 1


@pytest.mark.asyncio
async def test_scene_preserve_without_seedream_uses_fallback():
    router, pulid, seedream, fallback = _make_router(seedream=None)
    out = await router.generate(
        "prompt",
        reference_image=b"photo",
        params={"generation_mode": "scene_preserve"},
    )
    assert out == b"fallback-out"


@pytest.mark.asyncio
async def test_identity_scene_accepts_pre_supplied_face_crop():
    """When pulid_face_crop is in params the router skips detection."""
    router, pulid, _seedream, _fallback = _make_router()
    with patch(
        "src.providers.image_gen.style_router.crop_face_for_pulid",
    ) as mock_crop:
        out = await router.generate(
            "prompt",
            reference_image=b"photo",
            params={
                "generation_mode": "identity_scene",
                "pulid_face_crop": b"PRE-CROPPED-FACE",
            },
        )
    assert out == b"pulid-out"
    mock_crop.assert_not_called()
    assert pulid.seen[0]["ref_len"] == len(b"PRE-CROPPED-FACE")


def test_backend_summary_lists_all_three_backends():
    router, _pulid, _seedream, _fallback = _make_router()
    summary = router.backend_summary()
    assert set(summary) == {"pulid", "seedream", "fallback"}
    assert summary["fallback"] == "_Backend"


def test_constructor_requires_fallback():
    with pytest.raises(ValueError, match="fallback"):
        StyleRouter(pulid=None, seedream=None, fallback=None)


@pytest.mark.asyncio
async def test_routed_backend_contextvar_reflects_pulid_path():
    """v1.20: after an identity_scene → PuLID call the ContextVar = 'pulid'."""
    from src.providers.image_gen.style_router import get_routed_backend

    router, _pulid, _seedream, _fallback = _make_router()
    crop_ok = FaceCropResult(
        image_bytes=b"FACE", reason=FaceCropReason.OK,
    )
    with patch(
        "src.providers.image_gen.style_router.crop_face_for_pulid",
        return_value=crop_ok,
    ):
        await router.generate(
            "prompt",
            reference_image=b"photo",
            params={"generation_mode": "identity_scene"},
        )
    assert get_routed_backend() == "pulid"


@pytest.mark.asyncio
async def test_routed_backend_contextvar_reflects_fallback_on_crop_failure():
    """v1.20: identity_scene → scene_preserve fallback exposes 'seedream'."""
    from src.providers.image_gen.style_router import get_routed_backend

    router, _pulid, _seedream, _fallback = _make_router()
    crop_fail = FaceCropResult(
        image_bytes=None, reason=FaceCropReason.NO_FACE,
    )
    with patch(
        "src.providers.image_gen.style_router.crop_face_for_pulid",
        return_value=crop_fail,
    ):
        await router.generate(
            "prompt",
            reference_image=b"photo-no-face",
            params={"generation_mode": "identity_scene"},
        )
    assert get_routed_backend() == "seedream"


@pytest.mark.asyncio
async def test_routed_backend_contextvar_reflects_scene_preserve_path():
    from src.providers.image_gen.style_router import get_routed_backend

    router, _pulid, _seedream, _fallback = _make_router()
    await router.generate(
        "prompt",
        reference_image=b"photo",
        params={"generation_mode": "scene_preserve"},
    )
    assert get_routed_backend() == "seedream"


def test_cost_estimation_follows_routed_backend():
    """v1.20: router deg identity_scene→seedream costs $0.03, not $0.015."""
    from src.orchestrator.executor import _estimate_backend_cost

    label, cost = _estimate_backend_cost(
        "StyleRouter", "identity_scene", routed_backend="seedream",
    )
    assert label == "seedream"
    assert cost == pytest.approx(0.03, abs=1e-6)

    label2, cost2 = _estimate_backend_cost(
        "StyleRouter", "identity_scene", routed_backend="pulid",
    )
    assert label2 == "pulid"
    assert cost2 == pytest.approx(0.015, abs=1e-6)
