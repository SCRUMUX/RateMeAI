"""Document-photo aspect ratio is now a *local* crop, not a Reve param.

v1.13.3 moved AR handling for document CV styles into local PIL
post-processing (see src.services.postprocess.crop_to_aspect). These
tests cover:
  * the mapping table stays in sync;
  * the CV prompt builder still uses ID-style language for documents;
  * the document AR helper on the executor returns ``None`` for
    non-document styles so callers fall back to "no crop".
"""
from __future__ import annotations

from src.orchestrator.executor import _CV_DOCUMENT_ASPECT, _document_target_aspect
from src.prompts.image_gen import build_cv_prompt, is_document_style


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
    doc_prompt = build_cv_prompt(style="photo_3x4", gender="male").lower()
    assert "id-style headshot" in doc_prompt
    assert "neutral" in doc_prompt
    assert "professional attire" not in doc_prompt

    # v1.18: non-document CV styles run through the identity_scene
    # branch (PuLID) when the key falls through to the default spec.
    # The change instruction is replaced by the identity_scene opener,
    # so "professional attire" is no longer part of the prompt body —
    # the clothing line still carries the corporate outfit, and the
    # "reference person" anchor guarantees we are on the correct branch.
    normal_prompt = build_cv_prompt(style="ceo", gender="male").lower()
    assert "reference person" in normal_prompt
    assert "id-style headshot" not in normal_prompt
