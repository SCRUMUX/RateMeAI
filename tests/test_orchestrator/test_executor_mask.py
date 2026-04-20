"""Integration test: single-pass Reve call receives mask_image from segmentation.

Verifies that when `settings.segmentation_enabled=True` and a segmentation
service is wired in, the executor runs exactly ONE Reve call and that call
contains a PNG-encoded `mask_image` with region=background — satisfying
the "one Reve call, maximum quality" requirement.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


def _make_ok_report(face_area_ratio: float = 0.25) -> InputQualityReport:
    return InputQualityReport(
        can_generate=True,
        face_area_ratio=face_area_ratio,
        face_center_offset=0.05,
        blur_face=200.0,
        blur_full=200.0,
        width=1024,
        height=1024,
        yaw=0.0,
        pitch=0.0,
        hair_bg_contrast=0.5,
        num_faces=1,
    )


def _make_png_mask() -> Image.Image:
    """Simple L-mode binary mask for 'background'."""
    img = Image.new("L", (512, 512), color=0)
    for x in range(256):
        for y in range(512):
            img.putpixel((x, y), 255)
    return img


def _make_jpeg_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_single_pass_passes_mask_image_to_reve(mock_settings):
    """Single-pass Reve call must receive mask_image (PNG bytes) + mask_region=background."""
    mock_settings.segmentation_enabled = True
    mock_settings.multi_pass_enabled = False
    mock_settings.reve_test_time_scaling = 3
    mock_settings.identity_threshold = 0.70
    mock_settings.identity_max_retries = 0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False

    image_gen = MagicMock()
    reve_output = b"\xff\xd8\xff\xe0" + b"0" * 2048
    image_gen.generate = AsyncMock(return_value=reve_output)

    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"

    model_router = MagicMock()
    model_router.cheapest_cost = 0.02

    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.build_public_url = MagicMock(return_value="https://example/result.jpg")

    identity_svc = MagicMock()
    identity_svc.verify = MagicMock(return_value=(True, 0.85))

    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {"aesthetic_score": 7.0})
    )

    seg_svc = MagicMock()
    seg_svc.segment = AsyncMock(return_value={"background": _make_png_mask()})

    executor = ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        model_router=model_router,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
        embedding_getter=AsyncMock(return_value=[0.1] * 128),
        segmentation_getter=lambda: seg_svc,
    )

    image_bytes = _make_jpeg_stub()
    result_dict: dict = {"base_description": "test subject"}
    trace: dict = {"decisions": [], "steps": {}}

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yacht",
        image_bytes=image_bytes,
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace=trace,
        gender="male",
        input_quality=_make_ok_report(),
    )

    assert image_gen.generate.await_count == 1, (
        "single_pass must call Reve exactly ONCE"
    )
    _, kwargs = image_gen.generate.call_args
    params = kwargs.get("params") or {}

    assert "mask_image" in params, "mask_image must be passed to Reve"
    assert isinstance(params["mask_image"], (bytes, bytearray))
    assert params["mask_image"][:8] == b"\x89PNG\r\n\x1a\n", (
        "mask_image must be valid PNG bytes"
    )
    assert params.get("mask_region") == "background"

    seg_svc.segment.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_single_pass_skips_mask_when_segmentation_disabled(mock_settings):
    """When segmentation_enabled=False — no segmentation call, no mask in params."""
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.reve_test_time_scaling = 3
    mock_settings.identity_threshold = 0.70
    mock_settings.identity_max_retries = 0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False

    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=b"\xff\xd8\xff\xe0" + b"0" * 2048)
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    model_router = MagicMock()
    model_router.cheapest_cost = 0.02
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.build_public_url = MagicMock(return_value="https://example/result.jpg")
    identity_svc = MagicMock()
    identity_svc.verify = MagicMock(return_value=(True, 0.85))
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {"aesthetic_score": 7.0})
    )

    seg_svc = MagicMock()
    seg_svc.segment = AsyncMock(return_value={"background": _make_png_mask()})

    executor = ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        model_router=model_router,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
        embedding_getter=AsyncMock(return_value=[0.1] * 128),
        segmentation_getter=lambda: seg_svc,
    )

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yacht",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_make_ok_report(),
    )

    assert image_gen.generate.await_count == 1
    _, kwargs = image_gen.generate.call_args
    params = kwargs.get("params") or {}
    assert "mask_image" not in params
    seg_svc.segment.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_single_pass_upscale_disabled_for_small_face(mock_settings):
    """Small face (face_area_ratio < 0.15) must disable upscale_factor=2."""
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.reve_test_time_scaling = 3
    mock_settings.identity_threshold = 0.70
    mock_settings.identity_max_retries = 0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False

    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=b"\xff\xd8\xff\xe0" + b"0" * 2048)
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    model_router = MagicMock()
    model_router.cheapest_cost = 0.02
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.build_public_url = MagicMock(return_value="https://example/r.jpg")
    identity_svc = MagicMock()
    identity_svc.verify = MagicMock(return_value=(True, 0.85))
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {"aesthetic_score": 7.0})
    )

    executor = ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        model_router=model_router,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
        embedding_getter=AsyncMock(return_value=[0.1] * 128),
        segmentation_getter=None,
    )

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yacht",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_make_ok_report(face_area_ratio=0.08),
    )

    _, kwargs = image_gen.generate.call_args
    params = kwargs.get("params") or {}
    postproc = params.get("postprocessing") or []
    assert not any(p.get("process") == "upscale" for p in postproc), (
        "upscale must NOT be applied for tiny faces"
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_single_pass_upscale_enabled_for_normal_face(mock_settings):
    """Normal face (face_area_ratio >= 0.15) should get upscale_factor=2."""
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.reve_test_time_scaling = 3
    mock_settings.identity_threshold = 0.70
    mock_settings.identity_max_retries = 0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False

    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=b"\xff\xd8\xff\xe0" + b"0" * 2048)
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    model_router = MagicMock()
    model_router.cheapest_cost = 0.02
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.build_public_url = MagicMock(return_value="https://example/r.jpg")
    identity_svc = MagicMock()
    identity_svc.verify = MagicMock(return_value=(True, 0.85))
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {"aesthetic_score": 7.0})
    )

    executor = ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        model_router=model_router,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
        embedding_getter=AsyncMock(return_value=[0.1] * 128),
        segmentation_getter=None,
    )

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yacht",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_make_ok_report(face_area_ratio=0.25),
    )

    _, kwargs = image_gen.generate.call_args
    params = kwargs.get("params") or {}
    postproc = params.get("postprocessing") or []
    assert any(
        p.get("process") == "upscale" and p.get("upscale_factor") == 2
        for p in postproc
    ), "upscale x2 must be applied for normal-sized faces"
