"""VLM-driven identity retry loop in ``ImageGenerationExecutor.single_pass``.

v1.17 adds a one-shot retry: if the first FLUX pass comes back with
``identity_match`` below ``settings.identity_match_threshold`` (and the
VLM check itself did NOT blow up), ``single_pass`` calls the provider
again with a fresh seed and keeps whichever candidate has the higher
numeric score. These tests pin the contract in both directions:

* Retry IS triggered only on a low *numeric* score — not on a VLM
  exception (``quality_check_failed=True``).
* When the retry delivers a higher score we keep the retry result
  and bump ``result_dict["enhancement"]["generation_attempts"]`` to 2.
* When the retry is not better (or the VLM check fails on it) we keep
  the original first-pass result.
* The feature flag ``settings.identity_retry_enabled=False`` disables
  the whole branch even when the score is low.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


def _jpeg(color=(128, 128, 128), size: int = 512) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=color).save(buf, format="JPEG")
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


def _base_settings(mock_settings, *, retry_enabled: bool = True) -> None:
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_match_threshold = 7.0
    mock_settings.identity_match_soft_threshold = 5.0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False
    mock_settings.segmentation_enabled = False
    mock_settings.identity_retry_enabled = retry_enabled
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False
    mock_settings.pipeline_budget_max_usd = 0.10
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.02


def _build_executor(
    *,
    provider_outputs: list[bytes],
    gate_reports: list[dict],
):
    """Construct an executor whose image_gen and gate_runner return a
    queued sequence of outputs / reports — one entry per call."""
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(side_effect=list(provider_outputs))
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.get_url = AsyncMock(return_value="https://example/result.jpg")
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        side_effect=[(True, [], r) for r in gate_reports]
    )
    return (
        ImageGenerationExecutor(
            image_gen=image_gen,
            prompt_engine=prompt_engine,
            storage=storage,
            identity_svc_getter=lambda: MagicMock(),
            gate_runner_getter=lambda: gate_runner,
        ),
        image_gen,
        gate_runner,
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_retry_triggers_on_low_numeric_score_and_keeps_better_result(
    mock_settings,
):
    _base_settings(mock_settings)
    first_img = _jpeg((50, 50, 50))
    retry_img = _jpeg((200, 200, 200))
    executor, image_gen, _ = _build_executor(
        provider_outputs=[first_img, retry_img],
        gate_reports=[
            {"identity_match": 4.0, "quality_check_failed": False},
            {"identity_match": 8.5, "quality_check_failed": False},
        ],
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_jpeg(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert image_gen.generate.await_count == 2
    enhancement = result_dict["enhancement"]
    assert enhancement["generation_attempts"] == 2
    assert pytest.approx(enhancement["identity_match"], rel=1e-3) == 8.5


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_retry_keeps_original_when_retry_score_is_lower(mock_settings):
    _base_settings(mock_settings)
    first_img = _jpeg((50, 50, 50))
    retry_img = _jpeg((200, 200, 200))
    executor, image_gen, _ = _build_executor(
        provider_outputs=[first_img, retry_img],
        gate_reports=[
            {"identity_match": 5.5, "quality_check_failed": False},
            {"identity_match": 3.0, "quality_check_failed": False},
        ],
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_jpeg(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert image_gen.generate.await_count == 2
    enhancement = result_dict["enhancement"]
    # We still paid for 2 attempts (cost reporting), but kept the
    # original because the retry was worse.
    assert enhancement["generation_attempts"] == 2
    assert pytest.approx(enhancement["identity_match"], rel=1e-3) == 5.5


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_retry_skipped_when_vlm_check_failed(mock_settings):
    _base_settings(mock_settings)
    executor, image_gen, _ = _build_executor(
        provider_outputs=[_jpeg()],
        gate_reports=[{
            "identity_match": None,
            "quality_check_failed": True,
        }],
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_jpeg(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    # Retry on a VLM failure is intentionally off — there's no
    # numeric signal to improve against.
    assert image_gen.generate.await_count == 1
    assert result_dict["enhancement"]["generation_attempts"] == 1


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_retry_disabled_by_feature_flag(mock_settings):
    _base_settings(mock_settings, retry_enabled=False)
    executor, image_gen, _ = _build_executor(
        provider_outputs=[_jpeg()],
        gate_reports=[{
            "identity_match": 2.5,
            "quality_check_failed": False,
        }],
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_jpeg(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert image_gen.generate.await_count == 1
    assert result_dict["enhancement"]["generation_attempts"] == 1


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_retry_skipped_when_first_score_already_passes(mock_settings):
    _base_settings(mock_settings)
    executor, image_gen, _ = _build_executor(
        provider_outputs=[_jpeg()],
        gate_reports=[{
            "identity_match": 9.0,
            "quality_check_failed": False,
        }],
    )

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_jpeg(),
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert image_gen.generate.await_count == 1
    assert result_dict["enhancement"]["generation_attempts"] == 1
