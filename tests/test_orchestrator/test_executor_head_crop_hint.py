"""Regression tests for the head-crop proportion lock in
``ImageGenerationExecutor.single_pass``.

Telegram bot clients are physically capped at ``message.photo[-1]``
previews (~1280 px), which in practice are tight head-and-shoulders
crops with ``face_area_ratio > 0.35``. Edit models (NB2 / GPT-2)
preserve the head scale from the reference; on ``half_body`` /
``full_body`` framings they then draw a torso/legs at a smaller scale
around the same-sized head — the "oversized head, pasted face"
failure mode users reported after the A/B cutover.

The executor injects a positive-framed proportion-lock paragraph into
the prompt when all three conditions hold:

* ``face_area_ratio > 0.35`` (the same threshold the bot uses for the
  pre-generation reference-compat warning, see
  ``src/services/input_quality.py``);
* ``framing`` is ``half_body`` or ``full_body``;
* the style is NOT a document style (those always run ``portrait``).

These tests lock the trigger conditions so a future refactor can't
silently regress the guard. The hint is applied to the prompt that
reaches ``image_gen.generate`` — that is the wire-level contract.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


_HINT_FRAGMENT = "Composition note: the reference photo is a tight head-and-shoulders"


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
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.02
    mock_settings.pipeline_budget_max_usd = 0.10
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False
    mock_settings.gfpgan_preclean_enabled = False
    mock_settings.codeformer_enabled = False
    mock_settings.pulid_steps = 4
    mock_settings.ab_test_enabled = True
    mock_settings.ab_default_quality = "medium"
    mock_settings.variation_engine_v2_enabled = True


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
async def test_head_crop_hint_injected_on_half_body_with_tight_crop(mock_settings):
    """``face_area_ratio > 0.35`` + ``half_body`` framing on a non-doc
    style must inject the proportion-lock paragraph into the prompt.

    This is the exact failure mode that hit Telegram bot users after
    the A/B cutover — Telegram previews are tight crops, the bot
    defaulted to ``half_body`` framing, and the edit model produced
    an over-large head on a small torso.
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
    assert _HINT_FRAGMENT in prompt, (
        "Head-crop proportion lock missing from the prompt even though "
        f"face_area_ratio=0.45 > 0.35 and framing=half_body. Prompt: {prompt!r}"
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_head_crop_hint_injected_on_full_body_with_tight_crop(mock_settings):
    """Same trigger applies to ``full_body`` framing — the head/torso
    proportion mismatch is even more visible at full body."""
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
    assert _HINT_FRAGMENT in prompt


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_head_crop_hint_skipped_for_portrait_framing(mock_settings):
    """``portrait`` framing already matches the head-shot reference —
    the proportion lock would be redundant and could over-anchor the
    model on the original framing. Skip it."""
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
        framing="portrait",
    )

    prompt = _prompt_sent_to_provider(image_gen)
    assert _HINT_FRAGMENT not in prompt, (
        "Head-crop hint must not fire on portrait framing — the "
        "reference framing already matches."
    )


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_head_crop_hint_skipped_when_face_small(mock_settings):
    """Web uploads with a wide-shot reference (``face_area_ratio
    well below 0.35``) don't suffer the proportion clash — skip the
    hint so we don't add prompt budget for nothing."""
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
        input_quality=_report_with_face_ratio(0.15),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    prompt = _prompt_sent_to_provider(image_gen)
    assert _HINT_FRAGMENT not in prompt


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_head_crop_hint_uses_positive_framing_only(mock_settings):
    """The hint passes through the same positive-framing validator as
    every StyleSpec field — no ``no/without/avoid/don't`` tokens. This
    is the regression detector for ``_has_disallowed_negative`` in
    ``src/prompts/style_spec.py``: if a future maintainer rewrites the
    hint with negative phrasing it will fail the bot validator the
    moment someone tries to promote it into a StyleSpec.
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
        input_quality=_report_with_face_ratio(0.50),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="half_body",
    )

    prompt = _prompt_sent_to_provider(image_gen)
    hint_start = prompt.find(_HINT_FRAGMENT)
    assert hint_start >= 0
    hint = prompt[hint_start:]

    from src.prompts.style_spec import _has_disallowed_negative

    assert not _has_disallowed_negative(hint), (
        "Head-crop hint contains negative framing tokens "
        "(no/without/avoid/don't); rewrite in positive form. "
        f"Hint: {hint!r}"
    )
