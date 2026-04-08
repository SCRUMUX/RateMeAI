"""Tests for the pre-analyze feature: endpoint, pipeline cache, style metadata, bot formatting."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.enums import AnalysisMode


# ── Style catalog metadata ──

def test_style_catalog_all_entries_are_4_tuples():
    from src.services.style_catalog import STYLE_CATALOG
    for mode, items in STYLE_CATALOG.items():
        for i, entry in enumerate(items):
            assert len(entry) == 4, f"{mode}[{i}] has {len(entry)} elements, expected 4"
            key, label, hook, meta = entry
            assert isinstance(key, str), f"{mode}[{i}] key must be str"
            assert isinstance(label, str), f"{mode}[{i}] label must be str"
            assert isinstance(hook, str), f"{mode}[{i}] hook must be str"
            assert isinstance(meta, dict), f"{mode}[{i}] meta must be dict"
            assert meta["param"] in ("warmth", "presence", "appeal"), (
                f"{mode}[{i}] invalid param: {meta['param']}"
            )
            lo, hi = meta["delta_range"]
            assert 0 < lo < hi <= 1.0, f"{mode}[{i}] invalid delta_range: {meta['delta_range']}"


def test_get_catalog_json_includes_meta():
    from src.services.style_catalog import get_catalog_json
    items = get_catalog_json("dating")
    assert len(items) > 0
    for item in items:
        assert "meta" in item
        assert "param" in item["meta"]
        assert "delta_range" in item["meta"]


# ── Enhancement advisor: predict_style_delta ──

def test_predict_style_delta_returns_positive():
    from src.services.enhancement_advisor import predict_style_delta
    meta = {"param": "appeal", "delta_range": (0.25, 0.45)}
    param, delta = predict_style_delta(meta, user_id=12345, mode="dating")
    assert param == "appeal"
    assert 0.25 <= delta <= 0.45


def test_predict_style_delta_deterministic():
    from src.services.enhancement_advisor import predict_style_delta
    meta = {"param": "warmth", "delta_range": (0.15, 0.30)}
    _, d1 = predict_style_delta(meta, user_id=42, mode="cv")
    _, d2 = predict_style_delta(meta, user_id=42, mode="cv")
    assert d1 == d2


def test_enhancement_preview_includes_deltas():
    from src.services.enhancement_advisor import build_enhancement_preview
    preview = build_enhancement_preview("dating", user_id=777, depth=1, count=2)
    assert len(preview.suggestions) == 2
    for s in preview.suggestions:
        assert s.predicted_param in ("warmth", "presence", "appeal")
        assert s.predicted_delta > 0


def test_suggestion_line_includes_delta_text():
    from src.services.enhancement_advisor import EnhancementSuggestion
    s = EnhancementSuggestion(
        action="⛵ На яхте",
        effect="Морской кадр",
        style_key="yacht",
        predicted_param="appeal",
        predicted_delta=0.33,
    )
    assert "+0.33" in s.line
    assert "привлекательности" in s.line


# ── Redis key ──

def test_preanalysis_cache_key_format():
    from src.utils.redis_keys import preanalysis_cache_key
    key = preanalysis_cache_key("abc-123")
    assert key == "ratemeai:preanalysis:abc-123"


# ── Pipeline: cache hit / miss ──

_JPEG_STUB = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
    b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
    b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x08\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9"
)


def _build_pipeline_with_redis(cached_pre: dict | None = None):
    from src.orchestrator.pipeline import AnalysisPipeline

    llm = MagicMock()
    llm.close = AsyncMock()
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="k.jpg")
    storage.get_url = AsyncMock(return_value="http://test/k.jpg")
    storage.download = AsyncMock(return_value=b"gen_bytes" * 20)

    ig = MagicMock()
    ig.close = AsyncMock()
    ig.generate = AsyncMock(return_value=b"gen_bytes" * 20)

    redis_mock = AsyncMock()
    if cached_pre is not None:
        redis_mock.get = AsyncMock(return_value=json.dumps(cached_pre))
    else:
        redis_mock.get = AsyncMock(return_value=None)

    pipeline = AnalysisPipeline(llm=llm, storage=storage, image_gen=ig, redis=redis_mock)
    return pipeline, redis_mock


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.has_face_heuristic", return_value=True)
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_pipeline_uses_cached_pre_analysis(mock_nsfw, mock_norm, mock_face, mock_settings):
    """When pre_analysis_id is provided and cache exists, pipeline skips LLM analysis."""
    mock_settings.segmentation_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    cached = {
        "dating_score": 7.5,
        "first_impression": "Cached impression",
        "strengths": ["Good lighting"],
        "_scores_humanized": True,
    }
    pipeline, redis_mock = _build_pipeline_with_redis(cached_pre=cached)

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={"dating_score": 6})
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test prompt"
    pipeline._merger = MagicMock()
    pipeline._merger.merge.return_value = {"dating_score": 7.5, "cached": True}

    import asyncio
    asyncio.get_event_loop().run_until_complete(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_JPEG_STUB,
            user_id="u_cache",
            task_id="t_cache",
            context={"style": "yacht", "pre_analysis_id": "pre-123"},
        )
    )

    service_mock.analyze.assert_not_awaited()
    redis_mock.get.assert_awaited()


@patch("src.orchestrator.pipeline.settings")
@patch("src.orchestrator.pipeline.has_face_heuristic", return_value=True)
@patch("src.orchestrator.pipeline.validate_and_normalize", side_effect=lambda b: (b, {}))
@patch("src.orchestrator.pipeline.extract_nsfw_from_analysis", return_value=(True, ""))
def test_pipeline_cache_miss_runs_llm(mock_nsfw, mock_norm, mock_face, mock_settings):
    """When pre_analysis_id is provided but cache is empty, pipeline runs normal LLM analysis."""
    mock_settings.segmentation_enabled = False
    mock_settings.identity_threshold = 0.85
    mock_settings.identity_max_retries = 2
    mock_settings.model_cost_reve = 0.02
    mock_settings.model_cost_replicate = 0.05

    pipeline, redis_mock = _build_pipeline_with_redis(cached_pre=None)

    service_mock = MagicMock()
    service_mock.analyze = AsyncMock(return_value={
        "dating_score": 6,
        "first_impression": "Fresh analysis",
        "strengths": [],
    })
    pipeline._router = MagicMock()
    pipeline._router.get_service.return_value = service_mock
    pipeline._prompt_engine = MagicMock()
    pipeline._prompt_engine.build_image_prompt.return_value = "test prompt"
    pipeline._merger = MagicMock()
    pipeline._merger.merge.return_value = {"dating_score": 6}

    import asyncio
    asyncio.get_event_loop().run_until_complete(
        pipeline.execute(
            mode=AnalysisMode.DATING,
            image_bytes=_JPEG_STUB,
            user_id="u_miss",
            task_id="t_miss",
            context={"style": "yacht", "pre_analysis_id": "expired-id"},
        )
    )

    service_mock.analyze.assert_awaited_once()


# ── Bot message formatting ──

def test_format_pre_analysis_message_contains_score():
    from src.bot.handlers.mode_select import _format_pre_analysis_message
    data = {
        "pre_analysis_id": "abc",
        "score": 7.40,
        "first_impression": "Дружелюбный и открытый",
        "perception_scores": {"warmth": 7.14, "presence": 6.58, "appeal": 6.87},
        "enhancement_opportunities": ["Тёплое освещение", "Структурированная причёска"],
    }
    text = _format_pre_analysis_message("💕 *Образ для знакомств*", "dating", 123, data)
    assert "7.40" in text
    assert "Теплота" in text
    assert "Уверенность" in text
    assert "Привлекательность" in text
    assert "Дружелюбный и открытый" in text
    assert "Тёплое освещение" in text
    assert "Выбери стиль" in text


def test_format_pre_analysis_message_no_opportunities():
    from src.bot.handlers.mode_select import _format_pre_analysis_message
    data = {
        "pre_analysis_id": "xyz",
        "score": 8.00,
        "first_impression": "",
        "perception_scores": {"warmth": 8.0, "presence": 7.5, "appeal": 7.2},
        "enhancement_opportunities": [],
    }
    text = _format_pre_analysis_message("📸 *Образ для соцсетей*", "social", 456, data)
    assert "8.00" in text
    assert "Рекомендации" not in text
    assert "Выбери стиль" in text


# ── PreAnalysisResponse schema ──

def test_pre_analysis_response_schema():
    from src.models.schemas import PreAnalysisResponse
    resp = PreAnalysisResponse(
        pre_analysis_id="test-id",
        mode=AnalysisMode.DATING,
        first_impression="Nice",
        score=7.5,
        perception_scores={"warmth": 7.0, "presence": 6.5, "appeal": 7.2},
        perception_insights=[],
        enhancement_opportunities=["Smile more"],
    )
    d = resp.model_dump()
    assert d["pre_analysis_id"] == "test-id"
    assert d["mode"] == "dating"
    assert d["score"] == 7.5
    assert isinstance(d["perception_scores"], dict)
