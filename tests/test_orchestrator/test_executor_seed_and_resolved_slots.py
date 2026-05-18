"""Executor threads ``seed`` into the prompt engine and persists
``resolved_slots`` into ``result_dict`` (Stage 3 of the
prompt-pipeline-overhaul, 2026-05).

The slot sampler in the v3 prompt path needs an explicit seed so the
"Другой вариант" UI button can re-roll deterministically (the same
``request_id`` re-used for retries gives the same prompt; a fresh
seed gives a different one). This test pins the contract using a
mock prompt engine that records the kwargs it receives.

It also asserts the executor copies the ``out_resolved_slots`` map
(populated by the v3 path) into ``result_dict["resolved_slots"]`` so
the API response can return the rolled values to the frontend for
badge rendering.
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
    mock_settings.pipeline_budget_max_usd = 0.10
    mock_settings.identity_retry_enabled = False
    mock_settings.identity_retry_max_attempts = 1
    mock_settings.real_esrgan_enabled = False
    mock_settings.gfpgan_preclean_enabled = False
    mock_settings.codeformer_enabled = False
    mock_settings.pulid_steps = 4
    # v4.1: unified_prompt_v2_enabled flag removed; v3 path is now the
    # single path executor.single_pass takes.


class _RecordingPromptEngine:
    """Minimal prompt-engine double that records the seed it received
    and writes a stub roll into ``out_resolved_slots`` so we can verify
    the executor forwards both directions."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def build_image_prompt(self, *args, **kwargs):  # legacy entry-point
        return "TEST_PROMPT"

    def build_image_prompt_v2(self, *args, **kwargs):
        self.calls.append(dict(kwargs))
        slots = kwargs.get("out_resolved_slots")
        if isinstance(slots, dict):
            slots["trigger"] = "test trigger formulation"
            slots["lighting"] = "soft warm ambient"
            slots["weather"] = "clear"
        return "TEST_PROMPT_V2"


def _build_executor(image_gen, prompt_engine):
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
async def test_executor_forwards_seed_to_prompt_engine(mock_settings):
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())
    prompt_engine = _RecordingPromptEngine()
    executor = _build_executor(image_gen, prompt_engine)

    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=_make_jpeg_stub(),
        result_dict={"base_description": "test"},
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
        seed=12345,
    )

    assert prompt_engine.calls, "build_image_prompt_v2 was not invoked"
    kwargs = prompt_engine.calls[0]
    assert kwargs.get("seed") == 12345
    # The executor must hand the engine a *fresh* dict per call so the
    # v3 path can populate it without leaking between calls.
    assert isinstance(kwargs.get("out_resolved_slots"), dict)


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_executor_persists_resolved_slots_into_result_dict(mock_settings):
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())
    prompt_engine = _RecordingPromptEngine()
    executor = _build_executor(image_gen, prompt_engine)
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
        seed=42,
    )

    rolled = result_dict.get("resolved_slots")
    assert rolled is not None, "resolved_slots was not persisted"
    assert rolled["trigger"] == "test trigger formulation"
    assert rolled["lighting"] == "soft warm ambient"
    assert rolled["weather"] == "clear"


@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_executor_omits_resolved_slots_when_engine_writes_nothing(mock_settings):
    """When the v3 path is not taken (e.g. style is still v2), the
    prompt engine leaves ``out_resolved_slots`` empty. The executor
    must not pollute the result with an empty dict — frontend code
    branches on key presence to decide whether to render badges.
    """
    _base_settings(mock_settings)
    image_gen = MagicMock()
    image_gen.generate = AsyncMock(return_value=_make_png_stub())

    class _SilentEngine:
        def build_image_prompt(self, *a, **kw):
            return "TEST_PROMPT"

        def build_image_prompt_v2(self, *a, **kw):
            return "TEST_PROMPT_V2"

    prompt_engine = _SilentEngine()
    executor = _build_executor(image_gen, prompt_engine)
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

    assert "resolved_slots" not in result_dict
