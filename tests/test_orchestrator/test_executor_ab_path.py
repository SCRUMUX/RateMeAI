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
    # v1.23: A/B path has its own retry flag (defaults to OFF).
    mock_settings.ab_identity_retry_enabled = False
    # v1.24 Nano Banana 2 costs — high now matches medium (2K pixels,
    # the extra cost was 4K which we dropped; thinking=high is free).
    mock_settings.model_cost_fal_nano_banana_low = 0.08
    mock_settings.model_cost_fal_nano_banana_medium = 0.12
    mock_settings.model_cost_fal_nano_banana_high = 0.12
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
    # v1.23: A/B path must pass the NB2 aspect_ratio enum alongside
    # quality so the provider does not fall back to "auto" and crop
    # the head at 4K.
    assert params.get("aspect_ratio") in {
        "auto", "1:1", "4:5", "3:4", "2:3", "9:16", "16:9", "3:2", "4:3",
    }
    # v1.23: ``generation_mode`` is a PuLID/Seedream concept that NB2
    # does not understand. Executor must strip it before reaching A/B
    # providers so observability stays clean.
    assert "generation_mode" not in params
    # The prompt must come from the structured adapter, not from
    # ``prompt_engine.build_image_prompt``. v1.23 NB2 is prose, so we
    # check for the identity anchor instead of a block label.
    prompt = (args[0] if args else kwargs.get("prompt")) or ""
    assert (
        "Do not alter the person's face" in prompt
        or "Change:" in prompt
    )


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


# ----------------------------------------------------------------------
# v1.23: A/B path must skip legacy face-restoration steps
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@patch(
    "src.orchestrator.executor._maybe_real_esrgan_upscale",
    new_callable=AsyncMock,
)
@patch(
    "src.orchestrator.executor._apply_codeformer_post",
    new_callable=AsyncMock,
)
@patch("src.providers.factory.get_ab_image_gen")
@patch("src.orchestrator.executor.settings")
async def test_ab_path_skips_codeformer_and_real_esrgan(
    mock_settings, mock_get_ab, mock_codeformer, mock_upscale,
):
    """v1.23: on the A/B path the executor must NOT run CodeFormer or
    Real-ESRGAN. Both stages subtly re-render facial features and
    were the leading cause of identity drift in v1.22."""
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = True
    mock_settings.ab_identity_retry_enabled = False
    mock_settings.real_esrgan_enabled = True

    # Return anything truthy so the code path continues past the
    # post-processing block even if it were called.
    mock_codeformer.return_value = (_make_jpeg(), True)
    mock_upscale.return_value = _make_jpeg()

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

    mock_codeformer.assert_not_called()
    mock_upscale.assert_not_called()


@pytest.mark.asyncio
@patch("src.providers.factory.get_ab_image_gen")
@patch("src.orchestrator.executor.settings")
async def test_ab_path_skips_identity_retry_even_on_low_score(
    mock_settings, mock_get_ab,
):
    """v1.23: A/B path must NOT trigger identity retry. NB2 and GPT-2
    ignore the PuLID retry escalation params anyway, so a retry only
    doubles cost and latency without improving the face."""
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = True
    # Legacy retry flag ON — must be ignored on the A/B branch.
    mock_settings.identity_retry_enabled = True
    mock_settings.identity_retry_max_attempts = 1
    # Explicit A/B retry flag OFF.
    mock_settings.ab_identity_retry_enabled = False

    ab_provider = MagicMock()
    ab_provider.generate = AsyncMock(return_value=_make_jpeg())
    mock_get_ab.return_value = ab_provider

    default_image_gen = MagicMock()
    default_image_gen.generate = AsyncMock(return_value=_make_jpeg())
    executor, _ = _build_executor(default_image_gen)

    # Force the quality gate to report a low identity_match — this is
    # exactly the state that would trigger a retry on the legacy path.
    executor._get_gate_runner().run_global_gates = AsyncMock(
        return_value=(False, [], {
            "identity_match": 3.0,  # well below threshold 7.0
            "quality_check_failed": False,
            "aesthetic_score": 6.0,
            "gates_passed": [],
            "gates_failed": ["identity_match"],
        }),
    )

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
        ab_image_quality="medium",
    )

    # Exactly one generate call — no retry.
    assert ab_provider.generate.await_count == 1
