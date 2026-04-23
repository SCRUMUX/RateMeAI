"""Regression + feature tests for v1.21 A/B path in executor.single_pass.

Two invariants matter:

1. **Additive**: when ``ab_image_model=""`` the code path is bit-for-bit
   the same as before — the default ``self._image_gen`` provider runs,
   the prompt comes from ``PromptEngine.build_image_prompt``, and no
   import of ``src.prompts.ab_prompt`` is triggered.

2. **A/B switch**: when ``ab_image_model="nano_banana_2"`` (and the
   feature flag is on) the executor resolves the provider through
   ``get_ab_image_gen``, builds the prompt through
   ``build_structured_prompt``, forwards the quality tier via
   ``params["quality"]``, and — crucially — does NOT call the default
   ``self._image_gen.generate``.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.services.input_quality import InputQualityReport


def _make_jpeg(size: int = 512) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(128, 128, 128)).save(
        buf, format="JPEG",
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
    mock_settings.ab_test_enabled = True
    # v1.22: defaults flipped to the cheapest reliable combo.
    mock_settings.ab_default_model = "gpt_image_2"
    mock_settings.ab_default_quality = "low"
    mock_settings.ab_prompt_max_len = 1500
    # v1.22 Nano Banana 2 costs after the floor bump (1K/2K/4K).
    mock_settings.model_cost_fal_nano_banana_low = 0.08
    mock_settings.model_cost_fal_nano_banana_medium = 0.12
    mock_settings.model_cost_fal_nano_banana_high = 0.16
    # GPT Image 2 empirical per-tier averages.
    mock_settings.model_cost_gpt_image_2_low = 0.02
    mock_settings.model_cost_gpt_image_2_medium = 0.06
    mock_settings.model_cost_gpt_image_2_high = 0.25


def _build_executor(image_gen):
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "DEFAULT_PROMPT"
    storage = MagicMock()
    storage.upload = AsyncMock(return_value=None)
    storage.get_url = AsyncMock(return_value="https://example/result.jpg")
    identity_svc = MagicMock()
    gate_runner = MagicMock()
    gate_runner.run_global_gates = AsyncMock(
        return_value=(True, [], {
            "identity_match": 8.5,
            "quality_check_failed": False,
            "aesthetic_score": 7.5,
            "gates_passed": ["identity_match", "aesthetic_score"],
            "gates_failed": [],
        }),
    )
    return ImageGenerationExecutor(
        image_gen=image_gen,
        prompt_engine=prompt_engine,
        storage=storage,
        identity_svc_getter=lambda: identity_svc,
        gate_runner_getter=lambda: gate_runner,
    ), prompt_engine


# ----------------------------------------------------------------------
# Regression: default path untouched
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_default_path_when_ab_fields_missing(mock_settings):
    """``ab_image_model=""`` must run the legacy pipeline verbatim.

    Concretely: the default ``self._image_gen`` provider must be the
    one that gets ``generate()`` called on it, and the prompt must
    come from ``prompt_engine.build_image_prompt`` (not from the A/B
    structured builder).
    """
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_jpeg())
    executor, prompt_engine = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_make_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert image_gen.generate.await_count >= 1
    prompt_engine.build_image_prompt.assert_called()
    args, kwargs = image_gen.generate.await_args
    prompt_arg = args[0] if args else kwargs.get("prompt")
    assert prompt_arg == "DEFAULT_PROMPT"
    # Legacy path must NOT inject ``quality`` into params.
    params = kwargs.get("params") or {}
    assert "quality" not in params


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_default_path_when_feature_flag_off(mock_settings):
    """Even with ``ab_image_model="nano_banana_2"`` passed in, the
    executor must fall back to the default pipeline when the global
    ``ab_test_enabled`` flag is off."""
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = False
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_jpeg())
    executor, prompt_engine = _build_executor(image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_make_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
        ab_image_model="nano_banana_2",
        ab_image_quality="high",
    )

    assert image_gen.generate.await_count >= 1
    prompt_engine.build_image_prompt.assert_called()


# ----------------------------------------------------------------------
# A/B branch engaged
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@patch("src.providers.factory.get_ab_image_gen")
@patch("src.orchestrator.executor.settings")
async def test_ab_path_routes_through_ab_provider(
    mock_settings, mock_get_ab,
):
    """When ``ab_image_model="nano_banana_2"`` and the flag is on, the
    executor must call ``get_ab_image_gen("nano_banana_2").generate``
    instead of the default provider."""
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = True

    ab_provider = MagicMock()
    ab_provider.generate = AsyncMock(return_value=_make_jpeg())
    mock_get_ab.return_value = ab_provider

    default_image_gen = MagicMock()
    default_image_gen.generate = AsyncMock(return_value=_make_jpeg())
    executor, _ = _build_executor(default_image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_make_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
        ab_image_model="nano_banana_2",
        ab_image_quality="high",
    )

    # A/B provider must have been invoked at least once; default must
    # not have been called at all on the happy-path branch.
    assert ab_provider.generate.await_count >= 1
    default_image_gen.generate.assert_not_called()
    args, kwargs = ab_provider.generate.await_args
    params = kwargs.get("params") or {}
    assert params.get("quality") == "high"
    # The prompt must come from the structured adapter, not from
    # ``prompt_engine.build_image_prompt``.
    prompt = (args[0] if args else kwargs.get("prompt")) or ""
    assert "Subject:" in prompt or "Change:" in prompt


@pytest.mark.asyncio
@patch("src.providers.factory.get_ab_image_gen")
@patch("src.orchestrator.executor.settings")
async def test_ab_path_falls_back_on_provider_init_error(
    mock_settings, mock_get_ab,
):
    """If ``get_ab_image_gen`` raises (e.g. missing FAL key), the
    executor must fall back to the default pipeline rather than
    propagating the error upstream."""
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = True
    mock_get_ab.side_effect = RuntimeError("FAL_API_KEY missing")

    default_image_gen = MagicMock()
    default_image_gen.generate = AsyncMock(return_value=_make_jpeg())
    executor, prompt_engine = _build_executor(default_image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_make_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
        ab_image_model="nano_banana_2",
        ab_image_quality="medium",
    )

    assert default_image_gen.generate.await_count >= 1
    prompt_engine.build_image_prompt.assert_called()


@pytest.mark.asyncio
@patch("src.providers.factory.get_ab_image_gen")
@patch("src.orchestrator.executor.settings")
async def test_ab_path_defaults_to_configured_quality_when_not_provided(
    mock_settings, mock_get_ab,
):
    """v1.22: when the executor is handed an empty ``ab_image_quality``
    it must fall back to ``settings.ab_default_quality`` (now ``low``)."""
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = True
    mock_settings.ab_default_quality = "low"

    ab_provider = MagicMock()
    ab_provider.generate = AsyncMock(return_value=_make_jpeg())
    mock_get_ab.return_value = ab_provider

    default_image_gen = MagicMock()
    default_image_gen.generate = AsyncMock(return_value=_make_jpeg())
    executor, _ = _build_executor(default_image_gen)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        image_bytes=_make_jpeg(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
        ab_image_model="gpt_image_2",
        ab_image_quality="",
    )

    _, kwargs = ab_provider.generate.await_args
    params = kwargs.get("params") or {}
    assert params.get("quality") == "low"
