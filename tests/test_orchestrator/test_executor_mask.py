"""Integration test: single-pass Reve params + local post-processing (v1.13.3).

The executor must NOT leak any Reve-forbidden keys into the params dict
that reaches ``ImageGenProvider.generate``. Upscale and document AR are
now handled locally via ``src.services.postprocess``:

1. ``mask_region`` / ``mask_image`` / ``postprocessing`` / ``aspect_ratio``
   / ``test_time_scaling`` are absent from the provider call.
2. ``upscale_lanczos(factor=2)`` is invoked after generate when
   ``face_area_ratio >= 0.15``.
3. ``crop_to_aspect`` is invoked for CV document styles only.
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


_REVE_FORBIDDEN_KEYS = (
    "mask_region",
    "mask_image",
    "postprocessing",
    "test_time_scaling",
    "aspect_ratio",
)


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


def _make_jpeg_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _base_settings(mock_settings) -> None:
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_match_threshold = 7.0
    mock_settings.identity_match_soft_threshold = 5.0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False
    mock_settings.segmentation_enabled = False
    mock_settings.model_cost_reve = 0.02
    mock_settings.pipeline_budget_max_usd = 0.10
    # v1.17.1: these flags default True in production, but this file
    # asserts the legacy PIL LANCZOS path — pin them off so the tests
    # keep exercising exactly that branch.
    mock_settings.real_esrgan_enabled = False
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1


def _build_executor(
    *,
    image_gen_bytes: bytes | None = None,
) -> tuple[ImageGenerationExecutor, MagicMock]:
    if image_gen_bytes is None:
        image_gen_bytes = _make_png_stub()
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=image_gen_bytes)
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.get_url = AsyncMock(return_value="https://example/result.jpg")
    identity_svc = MagicMock()
    identity_svc.detect_face = MagicMock(return_value=True)
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {"aesthetic_score": 7.0, "identity_match": 8.5})
    )

    executor = ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
    )
    return executor, image_gen


def _assert_no_forbidden_keys(params: dict) -> None:
    for key in _REVE_FORBIDDEN_KEYS:
        assert key not in params, (
            f"forbidden Reve key {key!r} leaked into generate(params=...): {params!r}"
        )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_dating_params_have_no_forbidden_keys(mock_settings):
    _base_settings(mock_settings)
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
    _assert_no_forbidden_keys(params)


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_cv_params_have_no_forbidden_keys(mock_settings):
    _base_settings(mock_settings)
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
    _assert_no_forbidden_keys(params)


@pytest.mark.asyncio
@patch("src.orchestrator.executor.upscale_lanczos")
@patch("src.orchestrator.executor.settings")
async def test_upscale_disabled_for_small_face(mock_settings, mock_upscale):
    """upscale_lanczos must NOT be called when face_area_ratio < 0.15."""
    _base_settings(mock_settings)
    mock_upscale.return_value = _make_png_stub()
    executor, _ = _build_executor()

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

    mock_upscale.assert_not_called()


@pytest.mark.asyncio
@patch("src.orchestrator.executor.upscale_lanczos")
@patch("src.orchestrator.executor.settings")
async def test_upscale_enabled_for_normal_face(mock_settings, mock_upscale):
    """upscale_lanczos(factor=2) must run when face_area_ratio >= 0.15."""
    _base_settings(mock_settings)
    mock_upscale.return_value = _make_png_stub()
    executor, _ = _build_executor()

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

    mock_upscale.assert_called_once()
    _, kwargs = mock_upscale.call_args
    pos, _kw = mock_upscale.call_args
    assert pos[0] is not None
    assert kwargs.get("factor", pos[1] if len(pos) > 1 else None) == 2


@pytest.mark.asyncio
@patch("src.orchestrator.executor.crop_to_aspect")
@patch("src.orchestrator.executor.settings")
async def test_document_style_triggers_local_crop(mock_settings, mock_crop):
    """CV document styles should invoke crop_to_aspect(...) with the mapped AR."""
    _base_settings(mock_settings)
    mock_crop.return_value = _make_png_stub()
    executor, _ = _build_executor()

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="photo_3x4",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="female",
        input_quality=_make_ok_report(face_area_ratio=0.05),
    )

    mock_crop.assert_called_once()
    pos, _kw = mock_crop.call_args
    assert pos[1] == "3:4"


@pytest.mark.asyncio
@patch("src.orchestrator.executor.crop_to_aspect")
@patch("src.orchestrator.executor.settings")
async def test_non_document_style_skips_local_crop(mock_settings, mock_crop):
    """Non-document CV styles should NOT invoke crop_to_aspect(...)."""
    _base_settings(mock_settings)
    executor, _ = _build_executor()

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="ceo",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_make_ok_report(face_area_ratio=0.05),
    )

    mock_crop.assert_not_called()
