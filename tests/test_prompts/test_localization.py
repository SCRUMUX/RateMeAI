"""1.59.0 — language-aware analysis prompts.

Verifies that ``build_prompt(lang='en')`` in social/dating/cv flips
the prompt body and rule list into English, while the default
behaviour (no ``lang`` passed, no ``MARKET_ID`` env) stays Russian
for backward compatibility with the existing test corpus.
"""

from __future__ import annotations

import pytest

from src.prompts import cv, dating, social
from src.prompts.engine import PromptEngine
from src.prompts.perception import (
    _resolve_lang,
    get_perception_category_hints,
    get_perception_scoring_fields,
    get_perception_scoring_rules,
)
from src.models.enums import AnalysisMode


@pytest.mark.parametrize(
    "value, expected",
    [
        ("ru", "ru"),
        ("RU", "ru"),
        ("russian", "ru"),
        ("en", "en"),
        ("EN", "en"),
        ("english", "en"),
        ("global", "en"),
    ],
)
def test_resolve_lang_explicit(value, expected):
    assert _resolve_lang(value) == expected


def test_resolve_lang_unset_lang_uses_settings(monkeypatch):
    """When no explicit ``lang`` is passed, _resolve_lang reads
    ``settings.resolved_market_id``: ``ru`` → ru; ``global``/``en`` → en;
    anything else (incl. empty) → ru for backward compat with the
    legacy RU-only prompt corpus.
    """
    import src.config as _cfg

    class _S:
        def __init__(self, mid: str):
            self.resolved_market_id = mid

    monkeypatch.setattr(_cfg, "settings", _S("global"), raising=False)
    assert _resolve_lang() == "en"
    monkeypatch.setattr(_cfg, "settings", _S("ru"), raising=False)
    assert _resolve_lang() == "ru"
    monkeypatch.setattr(_cfg, "settings", _S(""), raising=False)
    assert _resolve_lang() == "ru"


@pytest.mark.parametrize("builder", [social.build_prompt, dating.build_prompt])
def test_analysis_prompts_explicit_russian(builder):
    p = builder({}, lang="ru")
    assert "Пиши на русском языке" in p
    assert '"warmth":' in p


@pytest.mark.parametrize("builder", [social.build_prompt, dating.build_prompt])
def test_analysis_prompts_switch_to_english(builder):
    p = builder({}, lang="en")
    assert "Write in English." in p
    # English perception block uses the same JSON keys but the
    # description in angle brackets must be translated.
    assert "how warm" in p
    assert '"warmth":' in p
    assert "Пиши на русском языке" not in p


def test_cv_prompt_localization():
    ru = cv.build_prompt({"profession": "designer"}, lang="ru")
    en = cv.build_prompt({"profession": "designer"}, lang="en")
    assert "designer" in ru and "designer" in en
    assert "Пиши на русском языке" in ru
    assert "Write in English." in en
    assert "you can strengthen" in en or "will add trust" in en


def test_cv_prompt_default_profession_translates():
    en = cv.build_prompt({}, lang="en")
    assert '"profession": "not specified"' in en


def test_perception_helpers_distinct_per_lang():
    ru_fields = get_perception_scoring_fields("ru")
    en_fields = get_perception_scoring_fields("en")
    assert ru_fields != en_fields
    assert "теплым" in ru_fields
    assert "trustworthy" in en_fields

    assert get_perception_scoring_rules("ru") != get_perception_scoring_rules("en")
    assert get_perception_category_hints("dating", "ru") != get_perception_category_hints(
        "dating", "en"
    )


def test_prompt_engine_passes_lang():
    engine = PromptEngine()
    en = engine.build(AnalysisMode.SOCIAL, lang="en")
    ru = engine.build(AnalysisMode.SOCIAL, lang="ru")
    assert "Write in English." in en
    assert "Пиши на русском языке" in ru


def test_prompt_engine_lang_silently_ignored_for_legacy_builders():
    # rating/emoji builders did not get the ``lang`` parameter — the
    # engine must silently fall back to the no-arg call instead of
    # raising.
    engine = PromptEngine()
    # Should not raise.
    engine.build(AnalysisMode.RATING, lang="en")
    engine.build(AnalysisMode.EMOJI, lang="en")
