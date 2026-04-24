"""v1.24.2 — executor.single_pass propagates ``ab_image_model`` into the
image_gen ``params`` dict.

Regression test for a silent A/B bug: when ``ab_test_enabled`` was on
and the caller asked for ``nano_banana_2``, executor.single_pass used
to pass only ``quality`` / ``aspect_ratio`` in ``extra``.
``UnifiedImageGenProvider._pick_backend`` reads ``params["image_model"]``
to route — without the key it always returned ``model_a`` (GPT-2), so
the explicit user choice was ignored until the catch-fallback fired.
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
    # v1.24.2 contract: ab_test_enabled is the gate for the A/B path.
    mock_settings.ab_test_enabled = True
    mock_settings.ab_default_quality = "medium"


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
async def test_ab_active_propagates_image_model_into_params(mock_settings):
    """``ab_image_model`` must land in ``params["image_model"]`` so the
    unified provider routes on it instead of defaulting to GPT-2.
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
        input_quality=_ok_report(),
        ab_image_model="nano_banana_2",
        ab_image_quality="high",
    )

    assert image_gen.generate.await_count >= 1
    _, kwargs = image_gen.generate.await_args
    params = kwargs.get("params") or {}
    assert params.get("image_model") == "nano_banana_2", (
        f"expected image_model=nano_banana_2 in params, got: {params!r}"
    )
    assert params.get("quality") == "high"


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_ab_active_propagates_gpt_image_2_model(mock_settings):
    """Symmetric case: when the caller picks GPT Image 2 the key still
    must be present so the unified provider doesn't have to guess.
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
        input_quality=_ok_report(),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
    )

    _, kwargs = image_gen.generate.await_args
    params = kwargs.get("params") or {}
    assert params.get("image_model") == "gpt_image_2"


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_ab_inactive_does_not_inject_image_model(mock_settings):
    """If A/B is off (or no model chosen), don't pollute params with an
    ``image_model`` key — the default hybrid path must stay untouched.
    """
    _base_settings(mock_settings)
    mock_settings.ab_test_enabled = False  # gate closed
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
        input_quality=_ok_report(),
        ab_image_model="nano_banana_2",  # requested but gate is closed
        ab_image_quality="medium",
    )

    _, kwargs = image_gen.generate.await_args
    params = kwargs.get("params") or {}
    # Hybrid StyleRouter path must NOT see ``image_model`` — that key is
    # A/B-exclusive.
    assert "image_model" not in params
