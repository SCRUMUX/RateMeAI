"""v1.66 — CV-mode reference-padding threshold boost.

When ``mode == AnalysisMode.CV`` and the requested style is NOT in the
studio-portrait whitelist (``formal_portrait`` / ``studio_elegant``)
the executor uses ``settings.csl_reference_pad_face_ratio_cv`` (0.22)
in place of the default ``csl_reference_pad_face_ratio`` (0.28). This
catches the "passport-style" selfies that CV users upload at much
higher rates than dating / social users.

These tests pin the exact boundary so a refactor cannot silently
drop the boost or extend it to the studio-portrait styles (which
are by-design tight headshots and would be over-padded).
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


def _report(*, face_area_ratio: float, composition_class: str = "portrait") -> InputQualityReport:
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
    mock_settings.csl_reference_pad_face_ratio = 0.28
    mock_settings.csl_reference_pad_face_ratio_cv = 0.22


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
async def test_cv_mode_pads_at_lowered_threshold(mock_settings, mock_pad):
    """CV style + face_area_ratio=0.25 (between cv-threshold 0.22 and
    default 0.28) MUST trigger padding because we use the lower CV
    threshold."""
    _base_settings(mock_settings)
    mock_pad.return_value = b"CV_PADDED"
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="legal_finance",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.25, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 1, (
        "CV-mode should pad at face_area_ratio=0.25 (CV threshold 0.22)"
    )


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_dating_mode_does_not_pad_at_same_threshold(mock_settings, mock_pad):
    """Same face_area_ratio=0.25 in DATING mode is BELOW the default
    0.28 threshold → no padding. This proves the boost is CV-only
    and doesn't accidentally widen padding for other modes."""
    _base_settings(mock_settings)
    mock_pad.return_value = b"NOT_USED"
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.25, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 0, (
        "DATING mode should NOT pad at face_area_ratio=0.25 — that is "
        "below the default threshold (0.28) and the CV boost must not "
        "leak to dating."
    )


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_cv_studio_portrait_does_not_use_boost(mock_settings, mock_pad):
    """``formal_portrait`` and ``studio_elegant`` are by-design tight
    headshots — they MUST NOT inherit the CV-mode boost, otherwise we
    over-pad a style that intentionally fills the frame with the
    head."""
    _base_settings(mock_settings)
    mock_pad.return_value = b"NOT_USED"
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_png())
    executor = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.CV,
        style="formal_portrait",
        image_bytes=_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_report(face_area_ratio=0.25, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 0, (
        "formal_portrait must not use the CV padding boost — it's an "
        "intentional tight headshot."
    )
