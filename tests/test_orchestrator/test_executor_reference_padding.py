"""Integration tests for the v1.64 + v1.65 + v1.67 reference-padding
gate in ``ImageGenerationExecutor.single_pass``.

The gate triggers on the "non-doc + portrait/half/full body framing +
non-full-body composition class (or face_area_ratio above threshold)"
cohort. v1.65 expanded the framing axis from ``(half_body, full_body)``
to ``(portrait, half_body, full_body)`` and decoupled the "tight"
threshold from the CSL classification threshold by introducing
``settings.csl_reference_pad_face_ratio`` (was 0.28; v1.67 lowered to
0.10). v1.67 also widened the composition_class trigger from
``("face_closeup", "unknown")`` to
``("face_closeup", "portrait", "half_body", "unknown")``: audit of
v1.66 traffic showed the "huge head" pathology persists on standard
half-body uploads with ``face_area_ratio ≈ 0.10..0.17`` because they
fell under the 0.28 default.

The only path that now skips padding is a true FULL_BODY upload
(face below 0.10 AND ample space below the chin) — that geometry
is already what the model would render, padding would be a no-op.

These tests pin the exact gate matrix so a future refactor cannot
silently widen it (e.g. padding document styles, which run a fixed
vendor-policy crop) or silently narrow it (skipping the gate when
it ought to fire).

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
    mock_settings.csl_reference_pad_face_ratio = 0.10
    mock_settings.csl_reference_pad_face_ratio_cv = 0.10


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
async def test_pad_fires_on_tight_selfie_portrait_framing(mock_settings, mock_pad):
    """v1.65: Portrait framing + tight-selfie reference → pad.

    Pre-v1.65 this case was the main miss of the gate: ``framing="portrait"``
    is the default in the web wizard and on bot inputs, so the most common
    tight-selfie request shape never got geometrically normalised. v1.65
    explicitly admits ``portrait`` into ``should_pad`` so the padding fires
    here.
    """
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_BYTES_PORTRAIT"
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

    assert mock_pad.call_count == 1
    _, call_kwargs = image_gen.generate.await_args
    assert call_kwargs["reference_image"] == b"PADDED_BYTES_PORTRAIT"


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_fires_on_portrait_class_above_pad_threshold(mock_settings, mock_pad):
    """v1.65: PORTRAIT-class upload with face_area_ratio just above the
    dedicated pad threshold (0.28) still triggers padding.

    The threshold is intentionally softer than the CSL FACE_CLOSEUP
    threshold (0.35) so the "huge head" pathology — which shows up on
    portrait-class uploads with above-typical face size — is corrected
    geometrically.
    """
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_PORTRAIT_30"
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
        # 0.30 > 0.28 pad threshold but < 0.35 CSL FACE_CLOSEUP threshold.
        input_quality=_report(face_area_ratio=0.30, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 1


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_fires_on_portrait_class_under_old_threshold(mock_settings, mock_pad):
    """v1.67: loose portrait upload (face_area_ratio 0.20, class
    PORTRAIT) NOW triggers padding.

    Pre-v1.67 this case was a regression hole: the 0.28 ratio gate +
    "face_closeup, unknown" class gate excluded portrait-class uploads,
    so a typical half-body selfie (face ~0.10..0.20) was sent to the
    edit-model unmodified — and the model copied the reference layout
    one-to-one, producing the "huge head" pathology. v1.67 widens
    both gates: PORTRAIT and HALF_BODY classes are now explicit
    triggers, and the ratio gate is lowered to 0.10.
    """
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_LOOSE_PORTRAIT"
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
        input_quality=_report(face_area_ratio=0.20, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 1


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
async def test_pad_skipped_only_for_true_full_body(mock_settings, mock_pad):
    """v1.67: a true full-body upload (face_area_ratio 0.05 + class
    FULL_BODY) is the only path that still skips padding.

    The classifier marks full-body when the face is small AND there's
    ample space below the chin — that geometry already matches the
    cinematic full-length-standing-shot target, so padding would be a
    no-op (worse: it would re-crop a valid full-body upload). We pin
    this lower edge so a future tweak cannot turn padding into an
    "every request" operation.
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
        # face_area 0.05 is below the 0.10 pad threshold, AND class is
        # FULL_BODY so neither gate fires.
        input_quality=_report(face_area_ratio=0.05, composition_class="full_body"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="full_body",
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
async def test_pad_fires_on_typical_half_body_upload_v167(mock_settings, mock_pad):
    """v1.67 regression guard — THE fix for the "huge head" pathology.

    The most common production upload shape is a half-body or
    head-and-shoulders photo with ``face_area_ratio`` around 0.10..0.17
    and ``composition_class`` = PORTRAIT. Before v1.67 this combination
    fell through every gate: ratio < 0.28, class not in
    ``("face_closeup", "unknown")``. The edit-model received the raw
    reference and copied its head/torso ratio verbatim — the user-
    facing pathology where every output had a disproportionately
    enlarged head, regardless of style.

    v1.67 widens the composition_class gate to include PORTRAIT and
    HALF_BODY explicitly AND lowers the ratio threshold to 0.10. This
    test pins both halves of the fix.
    """
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_TYPICAL_HALF_BODY"
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
        # face_area=0.13 is exactly the median half-body upload shape
        # and the audit-confirmed "huge head" trigger before v1.67.
        input_quality=_report(face_area_ratio=0.13, composition_class="portrait"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
    )

    assert mock_pad.call_count == 1, (
        "v1.67 regression: a typical half-body portrait upload "
        "(face_area_ratio=0.13, class=portrait) MUST trigger padding. "
        "If this assertion fires, the 'huge head' pathology will return."
    )
    _, call_kwargs = image_gen.generate.await_args
    assert call_kwargs["reference_image"] == b"PADDED_TYPICAL_HALF_BODY"


@pytest.mark.asyncio
@patch("src.services.reference_preprocess.pad_reference_for_framing")
@patch("src.orchestrator.executor.settings")
async def test_pad_fires_on_half_body_class_at_low_ratio_v167(mock_settings, mock_pad):
    """v1.67: HALF_BODY composition class is also an explicit padding
    trigger, even if face_area_ratio is well below 0.10.

    A half-body upload (face ~0.07, plenty of torso visible) still
    benefits from geometric normalisation when the requested framing
    is ``portrait`` — the canvas needs to be re-cropped to put the
    face in the right relative slot. Padding handles that locally
    without an extra FAL roundtrip.
    """
    _base_settings(mock_settings)
    mock_pad.return_value = b"PADDED_HALF_BODY_CLASS"
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
        input_quality=_report(face_area_ratio=0.07, composition_class="half_body"),
        ab_image_model="gpt_image_2",
        ab_image_quality="medium",
        framing="portrait",
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
