"""Tests for AnalysisPipeline (all external providers mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.models.enums import AnalysisMode
from src.orchestrator.pipeline import AnalysisPipeline
from src.services.input_quality import InputQualityReport


def _ok_report() -> InputQualityReport:
    return InputQualityReport(can_generate=True, face_area_ratio=0.2)


def _no_face_report() -> InputQualityReport:
    from src.services.input_quality import InputQualityIssue
    return InputQualityReport(
        can_generate=False,
        issues=[InputQualityIssue(
            code="no_face", severity="block",
            message="На фото не обнаружено лицо.",
            suggestion="Загрузите портрет.",
        )],
    )


def _make_jpeg_stub() -> bytes:
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
        b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
        b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x08\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9"
    )


def _build_pipeline(image_gen=None):
    llm = MagicMock()
    llm.close = AsyncMock()
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="k.jpg")
    storage.get_url = AsyncMock(return_value="http://test/k.jpg")
    storage.download = AsyncMock(return_value=b"gen_bytes" * 20)

    ig = image_gen or MagicMock()
    ig.close = AsyncMock()
    ig.generate = AsyncMock(return_value=b"gen_bytes" * 20)

    return AnalysisPipeline(llm=llm, storage=storage, image_gen=ig), llm, storage


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_execute_rating_mode(mock_nsfw, mock_norm, mock_face, mock_settings):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    rating_result = MagicMock()
    rating_result.model_dump.return_value = {
        "score": 7.5,
        "perception": {"trust": 8, "attractiveness": 7, "emotional_expression": "neutral"},
        "insights": ["Looks confident"],
        "recommendations": ["Smile more"],
    }
    rating_result.__class__.__name__ = "RatingResult"

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value=rating_result)
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._merger = MagicMock()
    pipeline._merger.merge.return_value = {"score": 7.5, "mode": "rating"}

    import asyncio
    result = asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.RATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u1",
            task_id="t1",
        )
    )
    assert result["score"] == 7.5
    service_mock.analyze.assert_awaited_once()


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_execute_dating_with_image_gen(mock_nsfw, mock_norm, mock_face, mock_settings):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 8,
        "first_impression": "Approachable",
        "strengths": ["Good smile"],
        "base_description": "person smiling",
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test prompt"
    pipeline._merger = MagicMock()
    pipeline._merger.merge.return_value = {
        "dating_score": 8,
        "generated_image_url": "http://test/k.jpg",
    }

    import asyncio
    result = asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u2",
            task_id="t2",
            context={"style": "warm_outdoor"},
        )
    )
    assert result.get("generated_image_url")
    pipeline._image_gen.generate.assert_awaited_once()


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_skip_image_gen_without_credits(mock_nsfw, mock_norm, mock_face, mock_settings):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 6,
        "base_description": "person",
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._merger = MagicMock()
    pipeline._merger.merge.return_value = {"dating_score": 6, "upgrade_prompt": True}

    import asyncio
    result = asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u3",
            task_id="t3",
            context={"skip_image_gen": True},
        )
    )
    assert result.get("upgrade_prompt") is True
    pipeline._image_gen.generate.assert_not_awaited()


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_execute_social_with_image_gen(mock_nsfw, mock_norm, mock_face, mock_settings):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "social_score": 7,
        "first_impression": "Bright profile",
        "strengths": ["Good lighting"],
        "weaknesses": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "social prompt"
    pipeline._merger = MagicMock()
    pipeline._merger.merge.return_value = {
        "social_score": 7,
        "generated_image_url": "http://test/k.jpg",
    }

    import asyncio
    result = asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.SOCIAL,
            image_bytes=_make_jpeg_stub(),
            user_id="u5",
            task_id="t5",
            context={"style": "influencer"},
        )
    )
    assert result.get("generated_image_url")
    pipeline._image_gen.generate.assert_awaited_once()


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_pipeline_trace_recorded(mock_nsfw, mock_norm, mock_face, mock_settings):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 8,
        "first_impression": "Good",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test"

    merged = {}
    def capture_merge(result, card, uid):
        merged.update(result)
        return result
    pipeline._merger = MagicMock()
    pipeline._merger.merge.side_effect = capture_merge

    import asyncio
    asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u6",
            task_id="t6",
            context={"style": "warm_outdoor"},
        )
    )
    trace = merged.get("pipeline_trace", {})
    assert "preprocess" in trace.get("steps", {})
    assert "analyze" in trace.get("steps", {})
    assert "generate_image" in trace.get("steps", {})
    assert trace.get("total_duration_ms", 0) > 0


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_delta_error_flagged_on_failure(mock_nsfw, mock_norm, mock_face, mock_settings):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()
    storage.download = AsyncMock(side_effect=Exception("storage down"))

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 8,
        "first_impression": "Good",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test"

    merged = {}
    def capture_merge(result, card, uid):
        merged.update(result)
        return result
    pipeline._merger = MagicMock()
    pipeline._merger.merge.side_effect = capture_merge

    import asyncio
    asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u7",
            task_id="t7",
            context={"style": "warm_outdoor"},
        )
    )
    assert merged.get("delta_error") == "rescoring_failed"


@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _no_face_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
def test_no_face_raises(mock_norm, mock_face):
    pipeline, _, _ = _build_pipeline()

    import asyncio
    from src.orchestrator.pipeline import PipelineStageError

    # After A1 every exception from a `_trace_step` block is wrapped in
    # PipelineStageError so the worker can tag it with its stage. The
    # original ValueError is available via `.original`.
    with pytest.raises(PipelineStageError) as ei:
        asyncio.run(
            pipeline.execute(
                mode=AnalysisMode.RATING,
                image_bytes=_make_jpeg_stub(),
                user_id="u4",
                task_id="t4",
            )
        )
    assert isinstance(ei.value.original, ValueError)
    assert "лицо" in str(ei.value.original)


# ----- Multi-pass pipeline tests (historical) -----
#
# Multi-pass execution is now reserved in ``src.orchestrator.advanced`` and
# is NOT wired into the runtime pipeline. The former scenarios
# (``test_multipass_dating_executes_plan``, ``test_multipass_fallback_on_error``,
# ``test_multipass_global_gates_fail_still_delivers``) exercised a path that
# the pipeline no longer reaches and have been removed. Coverage of the
# reserved machinery lives in ``tests/test_orchestrator/test_planner.py`` and
# ``tests/test_orchestrator/test_model_router.py``; direct coverage of
# ``AdvancedPipelineExecutor`` will land alongside the Scenario Engine epic.


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_decisions_logged_in_trace(mock_nsfw, mock_norm, mock_face, mock_settings):
    """Pipeline trace includes decision log entries."""
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 7, "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test"

    merged = {}
    def capture_merge(result, card, uid):
        merged.update(result)
        return result
    pipeline._merger = MagicMock()
    pipeline._merger.merge.side_effect = capture_merge

    import asyncio
    asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u12",
            task_id="t12",
        )
    )

    trace = merged.get("pipeline_trace", {})
    decisions = trace.get("decisions", [])
    assert len(decisions) > 0
    assert any("Single-pass" in d.get("decision", "") for d in decisions)


# ----------------------------------------------------------------------
# v1.24 regression — trace["steps"] must stay a dict on the A/B path
# ----------------------------------------------------------------------
#
# v1.23 shipped with ``trace.setdefault("steps", []).append({...})`` inside
# the ``if ab_active:`` branch of AnalysisPipeline._execute_inner. Because
# trace["steps"] is initialised as ``{}`` (a dict, not a list) the
# ``setdefault`` returned the existing dict and ``.append(...)`` blew up
# with ``AttributeError: 'dict' object has no attribute 'append'`` on
# every A/B generation — which is exactly the production error the user
# saw ("Remote AI processing failed: [stage=worker] AttributeError:
# 'dict' object has no attribute 'append'"). This test runs the pipeline
# with an A/B context and asserts that (a) no AttributeError is raised
# and (b) trace["steps"] stays a dict containing the face_prerestore
# entry written by the A/B branch.


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_ab_path_records_face_prerestore_without_crashing(
    mock_nsfw, mock_norm, mock_face, mock_settings,
):
    mock_settings.segmentation_enabled = False
    mock_settings.multi_pass_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.ab_test_enabled = True
    mock_settings.gfpgan_preclean_enabled = True
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 7,
        "base_description": "person",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test prompt"

    # Short-circuit the executor so the pipeline code path we care about
    # (trace writes around the A/B prerestore skip) runs but we don't
    # have to fully stub the image-gen branch.
    async def fake_single_pass(*args, **kwargs):
        trace = kwargs.get("trace") or (args[6] if len(args) > 6 else None)
        result_dict = kwargs.get("result_dict") or (args[3] if len(args) > 3 else None)
        if result_dict is not None:
            result_dict["generated_image_url"] = "http://example/ab.jpg"
        if trace is not None:
            # Mirror what the real executor would add; the dict integrity
            # check below still catches the v1.23 bug because we reach
            # this callback only AFTER the buggy .append() would have run.
            trace["steps"].setdefault("generate_image", {"info": "stub"})
        return None

    pipeline._executor.single_pass = AsyncMock(side_effect=fake_single_pass)

    merged: dict = {}
    def capture_merge(result, card, uid):
        merged.update(result)
        return result
    pipeline._merger = MagicMock()
    pipeline._merger.merge.side_effect = capture_merge

    import asyncio
    asyncio.run(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_make_jpeg_stub(),
            user_id="u_ab",
            task_id="t_ab",
            context={
                "style": "warm_outdoor",
                "image_model": "nano_banana_2",
                "image_quality": "high",
            },
        )
    )

    trace = merged.get("pipeline_trace", {})
    steps = trace.get("steps")
    assert isinstance(steps, dict), (
        "v1.23 regression: trace['steps'] must stay a dict on the A/B path; "
        "setdefault('steps', []).append(...) used to return the existing dict "
        "and raise AttributeError on every Nano Banana / GPT Image 2 run."
    )
    assert "face_prerestore" in steps
    assert steps["face_prerestore"].get("info", {}).get("applied") is False
    assert steps["face_prerestore"].get("info", {}).get("reason") == "ab_path_skip"


