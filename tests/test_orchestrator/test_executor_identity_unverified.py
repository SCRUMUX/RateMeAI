"""Executor surfaces an explicit warning when the VLM quality check fails
(v1.14.2 regression coverage).

Before 1.14.2 a VLM glitch (``_parse_json`` rejecting a JSON array, any
``compare_images`` exception, etc.) silently caused ``identity_match``
to be treated as a "pass". A mismatched photo was then delivered to the
user with no indication anything had gone wrong.

Now ``run_global_gates`` exposes ``quality_check_failed=True`` in the
report, and the executor turns that into:

    * ``result_dict["identity_unverified"] = True``
    * a user-facing warning in ``result_dict["generation_warnings"]``

so results.py can follow up with the reupload / accept keyboard.
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
    Image.new("RGB", (512, 512), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(200, 200, 200)).save(buf, format="PNG")
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
    # v1.17.1: production default flipped to True — keep legacy
    # single-attempt / LANCZOS semantics for these tests.
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False


def _build_executor(gate_report: dict, *, all_passed: bool = True):
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.get_url = AsyncMock(return_value="https://example/result.jpg")
    identity_svc = MagicMock()
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(return_value=(all_passed, [], gate_report))
    return ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_quality_check_failed_surfaces_unverified_warning(mock_settings):
    _base_settings(mock_settings)
    executor = _build_executor(
        gate_report={
            "identity_match": None,
            "quality_check_failed": True,
            "aesthetic_score": 7.0,
            "gates_passed": ["identity_match"],
            "gates_failed": [],
        }
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yoga_outdoor",
        image_bytes=_make_jpeg_stub(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert result_dict.get("identity_unverified") is True
    warnings = result_dict.get("generation_warnings", [])
    assert any("сходство" in w.lower() for w in warnings), (
        f"expected an identity-unverified warning, got: {warnings}"
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_successful_check_does_not_set_unverified(mock_settings):
    _base_settings(mock_settings)
    executor = _build_executor(
        gate_report={
            "identity_match": 8.5,
            "quality_check_failed": False,
            "aesthetic_score": 7.0,
            "gates_passed": ["identity_match", "aesthetic_score"],
            "gates_failed": [],
        }
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yoga_outdoor",
        image_bytes=_make_jpeg_stub(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert result_dict.get("identity_unverified") is not True
    warnings = result_dict.get("generation_warnings", [])
    assert not any("сходство" in w.lower() for w in warnings)


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_low_identity_match_keeps_legacy_soft_warning(mock_settings):
    """Numeric low score still triggers the pre-1.14.2 soft-threshold warning."""
    _base_settings(mock_settings)
    executor = _build_executor(
        gate_report={
            "identity_match": 3.5,  # below soft threshold 5.0
            "quality_check_failed": False,
            "aesthetic_score": 7.0,
            "gates_passed": [],
            "gates_failed": ["identity_match"],
        },
        all_passed=False,
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="yoga_outdoor",
        image_bytes=_make_jpeg_stub(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    warnings = result_dict.get("generation_warnings", [])
    assert any("Сильное отличие от оригинала" in w for w in warnings)
    # identity_unverified is reserved for quality_check_failed, not low scores.
    assert result_dict.get("identity_unverified") is not True
