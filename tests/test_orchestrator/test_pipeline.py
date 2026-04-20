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
    with pytest.raises(ValueError, match="лицо"):
        asyncio.run(
            pipeline.execute(
                mode=AnalysisMode.RATING,
                image_bytes=_make_jpeg_stub(),
                user_id="u4",
                task_id="t4",
            )
        )


# ----- Multi-pass pipeline tests -----

@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_multipass_dating_executes_plan(mock_nsfw, mock_norm, mock_face, mock_settings):
    """When multi_pass_enabled=True and mode=DATING, multi-pass plan is executed."""
    mock_settings.segmentation_enabled = True
    mock_settings.multi_pass_enabled = True
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05
    mock_settings.pipeline_budget_max_usd = 0.15
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = True
    mock_settings.photorealism_threshold = 0.5

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 8,
        "first_impression": "Good",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock

    from PIL import Image
    mock_mask = Image.new("L", (100, 100), 128)
    seg_mock = MagicMock()
    seg_mock.segment = AsyncMock(return_value={
        "face": mock_mask, "body": mock_mask,
        "background": mock_mask, "clothing": mock_mask,
        "full": mock_mask,
    })
    pipeline._segmentation = seg_mock

    from src.services.quality_gates import GateResult
    gate_mock = MagicMock()
    gate_mock.run_gates = AsyncMock(return_value=[
        GateResult("face_similarity", True, 0.95, 0.85),
    ])
    gate_mock.run_global_gates = AsyncMock(return_value=(
        True,
        [GateResult("face_similarity", True, 0.93, 0.85)],
        {"face_similarity": 0.93, "aesthetic_score": 7.5, "artifact_ratio": 0.01,
         "is_photorealistic": True, "gates_passed": ["face_similarity"], "gates_failed": []},
    ))
    pipeline._get_gate_runner = lambda: gate_mock

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
            user_id="u10",
            task_id="t10",
            context={"style": "warm_outdoor"},
        )
    )

    trace = merged.get("pipeline_trace", {})
    assert "execute_plan" in trace.get("steps", {})
    assert trace.get("decisions")
    assert any("Multi-pass" in d.get("decision", "") for d in trace["decisions"])
    assert merged.get("generated_image_url")
    assert merged.get("quality_report")
    assert merged.get("cost_breakdown")
    assert merged["enhancement"]["pipeline_type"] == "multi_pass"


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_multipass_fallback_on_error(mock_nsfw, mock_norm, mock_face, mock_settings):
    """Multi-pass failure does not trigger a second image-gen pass."""
    mock_settings.segmentation_enabled = True
    mock_settings.multi_pass_enabled = True
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05
    mock_settings.pipeline_budget_max_usd = 0.15
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = True
    mock_settings.photorealism_threshold = 0.5
    mock_settings.reve_test_time_scaling = 3

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 7,
        "first_impression": "OK",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock

    prompt_mock = MagicMock()
    prompt_mock.build_image_prompt.return_value = "fallback prompt"
    prompt_mock.build_step_prompt.return_value = "step prompt"
    pipeline._prompt_engine = prompt_mock
    pipeline._executor._prompt_engine = prompt_mock

    gate_mock = MagicMock()
    gate_mock.run_gates = AsyncMock(side_effect=Exception("gate runner exploded"))
    pipeline._get_gate_runner = lambda: gate_mock
    pipeline._executor._get_gate_runner = lambda: gate_mock

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
            user_id="u11",
            task_id="t11",
            context={"style": "warm_outdoor"},
        )
    )

    trace = merged.get("pipeline_trace", {})
    assert any(d.get("decision") == "Multi-pass failed" for d in trace.get("decisions", []))
    assert merged.get("generated_image_url") is None
    assert merged.get("image_gen_error") == "generation_failed"


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


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.analyze_input_quality", side_effect=lambda b: _ok_report())
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_multipass_global_gates_fail_still_delivers(mock_nsfw, mock_norm, mock_face, mock_settings):
    """When global gates fail, image is still delivered with quality_warning."""
    mock_settings.segmentation_enabled = True
    mock_settings.multi_pass_enabled = True
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05
    mock_settings.pipeline_budget_max_usd = 0.15
    mock_settings.aesthetic_threshold = 6.0
    mock_settings.artifact_threshold = 0.05
    mock_settings.photorealism_enabled = True
    mock_settings.photorealism_threshold = 0.5

    pipeline, llm, storage = _build_pipeline()

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 8,
        "first_impression": "Good",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock

    from PIL import Image
    mock_mask = Image.new("L", (100, 100), 128)
    seg_mock = MagicMock()
    seg_mock.segment = AsyncMock(return_value={
        "face": mock_mask, "body": mock_mask,
        "background": mock_mask, "clothing": mock_mask,
        "full": mock_mask,
    })
    pipeline._segmentation = seg_mock

    from src.services.quality_gates import GateResult
    gate_mock = MagicMock()
    gate_mock.run_gates = AsyncMock(return_value=[
        GateResult("face_similarity", True, 0.95, 0.85),
    ])
    gate_mock.run_global_gates = AsyncMock(return_value=(
        False,
        [
            GateResult("face_similarity", True, 0.93, 0.85),
            GateResult("aesthetic_score", False, 4.0, 6.0),
        ],
        {"face_similarity": 0.93, "aesthetic_score": 4.0, "artifact_ratio": 0.1,
         "is_photorealistic": False, "gates_passed": ["face_similarity"],
         "gates_failed": ["aesthetic_score"]},
    ))
    pipeline._get_gate_runner = lambda: gate_mock

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
            user_id="u13",
            task_id="t13",
            context={"style": "warm_outdoor"},
        )
    )

    assert merged.get("quality_warning") is True
    assert merged.get("generated_image_url")
    assert merged.get("quality_report")
    assert merged.get("cost_breakdown")
