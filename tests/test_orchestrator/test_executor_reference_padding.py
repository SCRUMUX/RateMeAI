"""Integration tests for the v1.64 reference-padding gate in
``ImageGenerationExecutor.single_pass``.

The gate triggers only on the "tight-selfie + non-doc + half/full body"
cohort. These tests pin the exact gate matrix so a future refactor
cannot silently widen it (e.g. running padding on every request,
which would corrupt portrait framings) or silently narrow it
(skipping the gate when it ought to fire).

We patch ``pad_reference_for_framing`` to a sentinel so the test asserts
on the boolean "was it called" — geometry correctness is covered by
:mod:`tests.test_services.test_reference_preprocess`.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _report(*, face_area_ratio: float, composition_class: str = "unknown") -> InputQualityReport:
    return InputQualityReport(
        can_generate=True,
        face_area_ratio=face_area_ratio,
        face_center_offset=0.05,
        blur_face=200.0,
        blur_full=200.0,
        width=1024,
        height=1024,
        face_bbox=(200, 150, 400, 500),
        yaw=0.0,
        pitch=0.0,
        hair_bg_contrast=0.5,
        num_faces=1,
        composition_class=composition_class,
    )


def _base_settings(mock_settings) -> None:
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_match_threshold = 7.0
    mock_settings.identity_match_soft_threshold = 5.0
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = False
    mock_settings.segmentation_enabled = False
    mock_settings.pipeline_budget_max_usd = 0.10
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False
    mock_settings.gfpgan_preclean_enabled = False
    mock_settings.codeformer_enabled = False
    mock_settings.ab_test_enabled = True
    mock_settings.ab_default_quality = "medium"
    mock_settings.variation_engine_v2_enabled = True
    mock_settings.csl_reference_pad_enabled = True
    mock_settings.csl_face_closeup_face_ratio = 0.35


def _build_executor(image_gen):
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
    prompt_engine.build_image_prompt_v2.return_value = "TEST_PROMPT"
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
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_fires_on_tight_selfie_half_body(mock_settings, mock_pad):
    """Tight selfie (face_closeup) + half_body + non-doc style → pad."""
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_BYTES"
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.45, composition_class="face_closeup"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    assert mock_pad.call_count == 1
    _, call_kwargs = image_gen.generate.await_args
    assert call_kwargs["reference_image"] == b"PADDED_BYTES"


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_skipped_on_portrait_framing(mock_settings, mock_pad):
    """Portrait already matches the tight-selfie aspect → no pad."""
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.45, composition_class="face_closeup"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 0


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_skipped_when_kill_switch_off(mock_settings, mock_pad):
    """``csl_reference_pad_enabled=False`` is a hard kill-switch."""
    _base_settings(mock_settings)
    mock_settings.csl_reference_pad_enabled = False
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.45, composition_class="face_closeup"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    assert mock_pad.call_count == 0


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_skipped_when_face_small(mock_settings, mock_pad):
    """Loose-crop input (face_area_ratio low, composition_class
    ``portrait``) does not need padding."""
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.12, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    assert mock_pad.call_count == 0


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_skipped_for_document_styles(mock_settings, mock_pad):
    """Document styles run portrait + fixed composition; they bypass
    the gate even if the input is tight."""
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="passport_rf",  # a document style key
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.45, composition_class="face_closeup"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    assert mock_pad.call_count == 0


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_fires_on_unknown_class_with_high_face_ratio(mock_settings, mock_pad):
    """``composition_class='unknown'`` is treated as tight-selfie under
    the fail-closed CSL policy. The gate fires on ``unknown`` for the
    same reason CSL itself fails closed there."""
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_BYTES_2"
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.42, composition_class="unknown"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="full_body",
    )

    assert mock_pad.call_count == 1


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_failure_falls_back_to_raw_reference(mock_settings, mock_pad):
    """If padding raises, the executor must log + send the raw image
    to the provider instead of failing the whole generation."""
    _base_settings(mock_settings)
    mock_pad.side_effect = RuntimeError("synthetic-fail")
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    raw = _jpeg()
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=raw,
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.45, composition_class="face_closeup"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    assert mock_pad.call_count == 1
    _, call_kwargs = image_gen.generate.await_args
    assert call_kwargs["reference_image"] == raw, (
        "Padding failure should fall back to the raw reference, not "
        "the sentinel"
    )
