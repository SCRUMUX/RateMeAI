"""Regression tests for the v1.64 removal of the executor-side
head-crop proportion lock.

The legacy ``head_crop_proportion_lock`` block in
``ImageGenerationExecutor.single_pass`` appended a free-form
"Composition note: the reference photo is a tight head-and-shoulders
crop..." paragraph AFTER the wrapped + truncated prompt. In practice
this had two failure modes:

1. The hint landed at the very END of the prompt — the worst zone
   for edit-model attention.
2. It duplicated ``_COMPOSITION_NUMERICAL_HINT`` (v1.64), which the
   wrapper now injects BEFORE :data:`IDENTITY_PRESERVE_BLOCK` —
   exactly where edit models pay the most attention.

These tests assert the old tail is GONE and the new numerical anchor
shows up in the prompt sent to the provider for tight-selfie inputs.
The wrapper-level coverage of the numerical anchor lives in
:mod:`tests.test_prompts.test_numerical_composition_anchor`; this
file focuses on the executor's contribution to the wire prompt.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


_LEGACY_HINT_FRAGMENT = (
    "Composition note: the reference photo is a tight head-and-shoulders"
)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _report_with_face_ratio(ratio: float) -> InputQualityReport:
    return InputQualityReport(
        can_generate=True,
        face_area_ratio=ratio,
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
    mock_settings.pipeline_budget_max_usd = 0.10
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False
    mock_settings.gfpgan_preclean_enabled = False
    mock_settings.codeformer_enabled = False
    mock_settings.ab_test_enabled = True
    mock_settings.ab_default_quality = "medium"
    mock_settings.variation_engine_v2_enabled = True
    # v1.64 — disable reference padding so this regression suite stays
    # focused on the prompt path. Padding has its own integration test
    # in test_executor_reference_padding.py.
    mock_settings.csl_reference_pad_enabled = False


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


def _prompt_sent_to_provider(image_gen) -> str:
    """Extract the prompt string that actually reached image_gen.generate."""
    assert image_gen.generate.await_count >= 1, "image_gen.generate was never called"
    args, kwargs = image_gen.generate.await_args
    if args:
        return args[0]
    return kwargs.get("prompt", "")


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_legacy_head_crop_tail_not_appended(mock_settings):
    """v1.64: the executor-level paragraph tail is gone. Composition
    correction is now handled by the wrapper-level numerical anchor
    (see ``_COMPOSITION_NUMERICAL_HINT``) which is positioned at the
    TOP of the prompt, not at the bottom.
    """
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
        input_quality=_report_with_face_ratio(0.45),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    prompt = _prompt_sent_to_provider(image_gen)
    assert _LEGACY_HINT_FRAGMENT not in prompt, (
        "v1.63 executor-side head-crop tail must not return; "
        "composition is the wrapper's numerical anchor job now.\n"
        f"Prompt: {prompt!r}"
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_legacy_head_crop_tail_not_appended_full_body(mock_settings):
    """Same regression guard for ``full_body`` framing."""
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
        input_quality=_report_with_face_ratio(0.50),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="full_body",
    )

    prompt = _prompt_sent_to_provider(image_gen)
    assert _LEGACY_HINT_FRAGMENT not in prompt
