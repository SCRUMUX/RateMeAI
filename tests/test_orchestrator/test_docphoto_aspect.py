"""Document-photo aspect ratio is a local PIL crop, not a vendor param.

v1.13.3 moved AR handling for document CV styles into local PIL
post-processing (see src.services.postprocess.crop_to_aspect). These
tests cover:
  * the mapping table stays in sync;
  * the CV prompt builder still uses ID-style language for documents;
  * the document AR helper on the executor returns ``None`` for
    non-document styles so callers fall back to "no crop".

v4.1 (May 2026): switched the prompt assertions from the removed
``build_cv_prompt`` helper to ``PromptEngine.build_image_prompt`` —
the only public entrypoint after the prompt-pipeline collapse.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.orchestrator.executor import _CV_DOCUMENT_ASPECT, _document_target_aspect
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import is_document_style


@pytest.fixture(scope="module", autouse=True)
def _ensure_styles_loaded():
    """Boot the v3 (with v2-promoted) registry before exercising prompts."""
    from src.services.style_loader_v2 import register_v2_styles_from_json
    from src.services.style_loader_v3 import register_v3_styles_from_json

    register_v2_styles_from_json()
    register_v3_styles_from_json()
    yield


def test_document_styles_have_explicit_aspect_ratio():
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
        assert _document_target_aspect(style) == ratio
        assert _CV_DOCUMENT_ASPECT.get(style) == ratio


def test_non_document_cv_style_has_no_target_aspect():
    for style in ("ceo", "tech", "creative", "medic", "", "unknown_style"):
        assert _document_target_aspect(style) is None


def test_document_style_detection():
    assert is_document_style("photo_3x4") is True
    assert is_document_style("passport_rf") is True
    assert is_document_style("visa_us") is True
    assert is_document_style("ceo") is False
    assert is_document_style("") is False


def test_cv_prompt_document_has_strict_instruction():
    # Document CV styles still follow the strict scene_preserve branch
    # with DOC_QUALITY / DOC_PRESERVE anchors. They MUST keep the
    # ID-style language and MUST NOT leak the non-doc "professional
    # attire" change instruction.
    engine = PromptEngine()
    doc_prompt = engine.build_image_prompt(
        AnalysisMode.CV, style="photo_3x4", gender="male"
    ).lower()
    assert "id-style headshot" in doc_prompt
    assert "neutral" in doc_prompt
    assert "professional attire" not in doc_prompt

    # Non-document CV style still routes through the v3 path. We
    # assert the new v4.1 opener mentions the reference photo and the
    # ID-style language stays clear of the non-doc prompt.
    normal_prompt = engine.build_image_prompt(
        AnalysisMode.CV, style="corporate", gender="male"
    ).lower()
    assert "reference photo" in normal_prompt
    assert "id-style headshot" not in normal_prompt
