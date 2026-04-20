"""Integration test: single-pass params plumbing for Reve.

After the mask_image regression (Reve SDK 0.1.2 does not accept mask_image in
edit(), see reve_provider.py), the executor now relies on a textual hint
driven by `mask_region` in the params. These tests verify:

1. `mask_region="background"` is ALWAYS set for CV/DATING/SOCIAL, regardless
   of segmentation state — this keeps the "change only background" hint in
   the prompt even when mediapipe is off.
2. Real `mask_image` bytes are only ever attached when
   `settings.segmentation_enabled=True` (future-proofing for when the SDK
   gains mask support).
3. `upscale_factor=2` is conditional on face_area_ratio >= 0.15 (unchanged
   from the original fix).
4. Exactly ONE Reve call per single_pass (cost invariant).
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


def _base_settings(mock_settings) -> None:
    mock_settings.multi_pass_enabled = False
    mock_settings.reve_test_time_scaling = 3
    mock_settings.identity_match_threshold = 7.0
    mock_settings.identity_match_soft_threshold = 5.0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False


def _build_executor(
    seg_svc=None,
    *,
    image_gen_bytes: bytes = b"\xff\xd8\xff\xe0" + b"0" * 2048,
) -> tuple[ImageGenerationExecutor, MagicMock]:
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=image_gen_bytes)
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    model_router = MagicMock()
    model_router.cheapest_cost = 0.02
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.build_public_url = MagicMock(return_value="https://example/result.jpg")
    identity_svc = MagicMock()
    identity_svc.detect_face = MagicMock(return_value=True)
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {"aesthetic_score": 7.0, "identity_match": 8.5})
    )

    executor = ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        model_router=model_router,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
        segmentation_getter=(lambda: seg_svc) if seg_svc is not None else None,
    )
    return executor, image_gen


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_mask_region_always_set_for_dating_without_segmentation(mock_settings):
    """With segmentation OFF (prod default) DATING must still carry
    mask_region=background so reve_provider can attach the text hint."""
    _base_settings(mock_settings)
    mock_settings.segmentation_enabled = False

    executor, image_gen = _build_executor()

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
    assert params.get("mask_region") == "background", (
        "mask_region must be set so reve_provider can prepend the text hint"
    )
    assert "mask_image" not in params, (
        "real mask_image must NOT leak to SDK when segmentation is disabled"
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_mask_region_always_set_for_cv(mock_settings):
    """CV mode must also get mask_region=background (document + business headshots)."""
    _base_settings(mock_settings)
    mock_settings.segmentation_enabled = False

    executor, image_gen = _build_executor()

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="ceo",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_make_ok_report(),
    )

    _, kwargs = image_gen.generate.call_args
    params = kwargs.get("params") or {}
    assert params.get("mask_region") == "background"


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_segmentation_flag_attaches_real_mask_image(mock_settings):
    """Future-proof: when segmentation_enabled=True, the executor must attach
    PNG mask_image bytes alongside mask_region. This exercises the code path
    that will be re-activated once the Reve SDK accepts mask_image."""
    _base_settings(mock_settings)
    mock_settings.segmentation_enabled = True

    seg_svc = MagicMock()
    seg_svc.segment = AsyncMock(return_value={"background": _make_png_mask()})

    executor, image_gen = _build_executor(seg_svc=seg_svc)

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
    assert "mask_image" in params
    assert isinstance(params["mask_image"], (bytes, bytearray))
    assert params["mask_image"][:8] == b"\x89PNG\r\n\x1a\n"
    assert params.get("mask_region") == "background"
    seg_svc.segment.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_single_pass_upscale_disabled_for_small_face(mock_settings):
    """Small face (face_area_ratio < 0.15) must disable upscale_factor=2."""
    _base_settings(mock_settings)
    mock_settings.segmentation_enabled = False

    executor, image_gen = _build_executor()

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
    _base_settings(mock_settings)
    mock_settings.segmentation_enabled = False

    executor, image_gen = _build_executor()

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
