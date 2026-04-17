"""Tests for document-photo aspect-ratio mapping and CV prompt specialization."""
from __future__ import annotations

from src.orchestrator.executor import _cv_style_aspect_ratio, _CV_DOCUMENT_ASPECT
from src.prompts.image_gen import build_cv_prompt, is_document_style


def test_document_styles_have_explicit_aspect_ratio():
    """Все CV-стили «Фото на документы» должны иметь явный aspect_ratio, не 'auto'."""
    expected = {
        "photo_3x4": "3:4",
        "passport_rf": "3:4",
        "visa_eu": "3:4",
        "visa_schengen": "3:4",
        "visa_us": "1:1",
        "photo_4x6": "2:3",
        "driver_license": "3:4",
    }
    for style, ratio in expected.items():
        assert _cv_style_aspect_ratio(style) == ratio, (
            f"document style {style} must map to aspect {ratio}, got {_cv_style_aspect_ratio(style)}"
        )
        assert _CV_DOCUMENT_ASPECT.get(style) == ratio


def test_non_document_cv_style_uses_auto_aspect_ratio():
    """Обычные CV-стили сохраняют 'auto' чтобы Reve сам подгонял под reference."""
    for style in ("ceo", "tech", "creative", "medic", "", "unknown_style"):
        assert _cv_style_aspect_ratio(style) == "auto"


def test_document_style_detection():
    """Хелпер должен различать document vs обычные CV-стили."""
    assert is_document_style("photo_3x4") is True
    assert is_document_style("passport_rf") is True
    assert is_document_style("visa_us") is True
    assert is_document_style("ceo") is False
    assert is_document_style("") is False


def test_cv_prompt_document_has_strict_instruction():
    """Для document-стилей промт должен требовать нейтральный фон/одежду
    и использовать softened ID-style язык (а не generic «professional attire»).
    Формулировки смягчили ради content-safety, но смысл сохранён.
    """
    doc_prompt = build_cv_prompt(style="photo_3x4", gender="male").lower()
    assert "id-style headshot" in doc_prompt or "id-style" in doc_prompt
    assert "neutral" in doc_prompt
    # Generic CV-ветка не должна активироваться для document-стиля.
    assert "professional attire" not in doc_prompt

    normal_prompt = build_cv_prompt(style="ceo", gender="male").lower()
    assert "professional attire" in normal_prompt
