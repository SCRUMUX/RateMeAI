"""Executor threads ``generation_mode`` into image-gen params (v1.18).

The hybrid pipeline relies on the StyleRouter picking PuLID vs Seedream
based on ``params["generation_mode"]``. Previously executor.single_pass
only passed ``seed`` and ``image_size``; v1.18 also has to forward the
style's ``generation_mode`` so the router can route correctly.

These tests pin that contract using a mocked image-gen provider that
records the params it receives.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


def _make_jpeg_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(128, 128, 128)).save(
        buf,
        format="JPEG",
    )
    return buf.getvalue()


def _make_png_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(200, 200, 200)).save(
        buf,
        format="PNG",
    )
    return buf.getvalue()


def _ok_report() -> InputQualityReport:
    return InputQualityReport(
        can_generate=True,
        face_area_ratio=0.25,
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


def _base_settings(mock_settings) -> None:
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_match_threshold = 7.0
    mock_settings.identity_match_soft_threshold = 5.0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False
    mock_settings.segmentation_enabled = False
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.02
    mock_settings.pipeline_budget_max_usd = 0.10
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False
    mock_settings.gfpgan_preclean_enabled = False
    mock_settings.codeformer_enabled = False
    mock_settings.pulid_steps = 4


def _build_executor(image_gen):
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.get_url = AsyncMock(return_value="https://example/result.jpg")
    identity_svc = MagicMock()
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(
            True,
            [],
            {
                "identity_match": 8.5,
                "quality_check_failed": False,
                "aesthetic_score": 7.5,
                "gates_passed": ["identity_match", "aesthetic_score"],
                "gates_failed": [],
            },
        ),
    )
    return ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_generation_mode_forwarded_from_style_spec(mock_settings):
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",  # identity_scene style in the registry
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert image_gen.generate.await_count >= 1
    _, kwargs = image_gen.generate.await_args
    params = kwargs.get("params") or {}
    assert "generation_mode" in params
    assert params["generation_mode"] in (
        "identity_scene",
        "scene_preserve",
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_document_style_forwards_scene_preserve_mode(mock_settings):
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="photo_3x4",  # strict document → scene_preserve
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    _, kwargs = image_gen.generate.await_args
    params = kwargs.get("params") or {}
    assert params.get("generation_mode") == "scene_preserve"


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_backend_label_propagates_into_enhancement_metadata(
    mock_settings,
):
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())
    executor = _build_executor(image_gen)

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_make_jpeg_stub(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    enhancement = result_dict.get("enhancement", {})
    assert "backend" in enhancement
    assert "generation_mode" in enhancement
    assert enhancement["generation_mode"] in (
        "identity_scene",
        "scene_preserve",
    )
