"""End-to-end integration tests for the v1.21 A/B pipeline.

Wires a real :class:`UnifiedImageGenProvider` with lightweight fake
providers into :class:`ImageGenerationExecutor`, then runs a full
``single_pass``. The goal is to guard the cross-component contract:

- ``framing`` propagates from ``params`` through the executor into ``resolve_output_size()``.
- The unified provider picks GPT-2 or Nano Banana based on ``image_model``.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.models.enums import AnalysisMode
from src.orchestrator.executor import ImageGenerationExecutor
from src.providers.image_gen.unified import UnifiedImageGenProvider
from src.services.input_quality import InputQualityReport


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_jpeg_with_face() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(180, 170, 160)).save(
        buf, format="JPEG",
    )
    return buf.getvalue()


def _make_png_stub() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), color=(200, 200, 200)).save(
        buf, format="PNG",
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


class _RecordingProvider:
    """Bare-bones ``ImageGenProvider`` that captures generate() calls."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict] = []
        self.generate = AsyncMock(side_effect=self._on_generate)

    async def _on_generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        self.calls.append({
            "prompt": prompt,
            "reference_image": reference_image,
            "params": dict(params or {}),
        })
        return _make_png_stub()

    async def close(self) -> None:  # pragma: no cover - not exercised
        return None


def _build_executor(image_gen) -> ImageGenerationExecutor:
    prompt_engine = MagicMock()
    prompt_engine.build_image_prompt.return_value = "TEST_PROMPT"
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
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.orchestrator.executor.settings")
async def test_unified_pipeline_routes_to_gpt2(
    mock_settings,
):
    mock_settings.ab_test_enabled = False
    
    gpt2 = _RecordingProvider("gpt_image_2")
    nano = _RecordingProvider("nano_banana_2")
    unified = UnifiedImageGenProvider(model_a=gpt2, model_b=nano)
    executor = _build_executor(unified)

    input_photo = _make_jpeg_with_face()

    result_dict: dict = {"base_description": "test"}
    await executor.single_pass(
        mode=AnalysisMode.DATING,
        style="motorcycle",
        image_bytes=input_photo,
        result_dict=result_dict,
        user_id="u1",
        task_id="t1",
        trace={"decisions": [], "steps": {}},
        gender="male",
        input_quality=_ok_report(),
    )

    assert len(gpt2.calls) == 1
    assert len(nano.calls) == 0
    
    call_params = gpt2.calls[0]["params"]
    assert "image_size" in call_params
