"""Tests for input-quality issue-text localisation.

1.58.0 introduced market-aware issue texts so the EN deployment renders
English copy and the RU edge keeps the original Russian set. This test
exercises the lookup helpers and the legacy proxy.
"""

from __future__ import annotations

import pytest

from src.services import photo_requirements as pr


def test_issue_texts_ru_contains_known_code():
    text = pr.get_issue_text(pr.IssueCode.HAIR_BG_SIMILAR, market_id="ru")
    assert text["message"].startswith("Волосы")
    assert "однотонн" in text["suggestion"]


def test_issue_texts_en_for_global_market():
    text = pr.get_issue_text(pr.IssueCode.HAIR_BG_SIMILAR, market_id="global")
    # English copy must not contain the Russian word "Волосы".
    assert text["message"] == "Hair blends into the background."
    assert "uniform background" in text["suggestion"]


def test_issue_texts_en_default_for_unknown_market():
    # Anything that is not exactly "ru" must resolve to English so an
    # unrecognised market id never accidentally shows Russian copy on
    # the global build.
    text = pr.get_issue_text(pr.IssueCode.NO_FACE, market_id="something-else")
    assert text["message"].startswith("No face detected")


@pytest.mark.parametrize(
    "code",
    [
        pr.IssueCode.INVALID_IMAGE,
        pr.IssueCode.LOW_RESOLUTION,
        pr.IssueCode.BLURRY_PHOTO,
        pr.IssueCode.NO_FACE,
        pr.IssueCode.FACE_TOO_SMALL,
        pr.IssueCode.FACE_BLURRED,
        pr.IssueCode.MULTIPLE_FACES,
        pr.IssueCode.FACE_SMALL_WARN,
        pr.IssueCode.FACE_OFF_CENTER,
        pr.IssueCode.NOT_FRONTAL,
        pr.IssueCode.HAIR_BG_SIMILAR,
        pr.IssueCode.FACE_DETECTOR_UNAVAILABLE,
        pr.IssueCode.FACE_TOO_TIGHT_FOR_BODY_SHOT,
    ],
)
def test_every_code_has_ru_and_en(code: str):
    ru = pr.get_issue_text(code, market_id="ru")
    en = pr.get_issue_text(code, market_id="global")
    assert ru["message"] and ru["suggestion"], f"missing RU copy for {code}"
    assert en["message"] and en["suggestion"], f"missing EN copy for {code}"


def test_legacy_issue_texts_proxy_uses_active_market(monkeypatch):
    # When the active market is global the legacy ``ISSUE_TEXTS[code]``
    # access pattern (used in src/services/input_quality.py) must yield
    # the English entry. ``resolved_market_id`` on the Settings model is
    # a read-only property, so we patch the helper that derives the
    # active language inside photo_requirements directly.
    monkeypatch.setattr(pr, "_resolve_lang", lambda *_args, **_kw: "en")
    entry = pr.ISSUE_TEXTS[pr.IssueCode.NO_FACE]
    assert entry["message"].startswith("No face detected")

    monkeypatch.setattr(pr, "_resolve_lang", lambda *_args, **_kw: "ru")
    entry_ru = pr.ISSUE_TEXTS[pr.IssueCode.NO_FACE]
    assert entry_ru["message"].startswith("На фото не обнаружено лицо")


# ---------------------------------------------------------------------------
# 1.59.0 — REQUIREMENTS_BULLETS / REJECT_BULLETS / *_plaintext localisation
# ---------------------------------------------------------------------------


def test_requirements_bullets_localised_per_market():
    ru = pr.get_requirements_bullets(market_id="ru")
    en = pr.get_requirements_bullets(market_id="global")
    assert len(ru) == len(en) == 6
    assert any("Лицо крупно" in b for b in ru)
    assert any("Face is large" in b for b in en)


def test_reject_bullets_localised_per_market():
    ru = pr.get_reject_bullets(market_id="ru")
    en = pr.get_reject_bullets(market_id="global")
    assert len(ru) == len(en) == 5
    assert any("400×400" in b for b in ru)
    assert any("400×400" in b for b in en)
    assert any("скриншот" in b for b in ru)
    assert any("screenshots" in b for b in en)


def test_format_requirements_plaintext_localised():
    ru = pr.format_requirements_plaintext(market_id="ru")
    en = pr.format_requirements_plaintext(market_id="global")
    assert ru.startswith("*Требования к фото:*")
    assert "*Не будет обработано:*" in ru
    assert en.startswith("*Photo requirements:*")
    assert "*Will not be processed:*" in en


def test_short_requirements_block_localised():
    ru = pr.short_requirements_block(market_id="ru")
    en = pr.short_requirements_block(market_id="global")
    assert ru.startswith("*Требования к фото:*")
    assert "/photo\\_help" in ru
    assert en.startswith("*Photo requirements:*")
    assert "/photo\\_help" in en


def test_legacy_bullets_proxy_uses_active_market(monkeypatch):
    monkeypatch.setattr(pr, "_resolve_lang", lambda *_args, **_kw: "en")
    assert any("Face is large" in b for b in pr.REQUIREMENTS_BULLETS)
    assert any("screenshots" in b for b in pr.REJECT_BULLETS)

    monkeypatch.setattr(pr, "_resolve_lang", lambda *_args, **_kw: "ru")
    assert any("Лицо крупно" in b for b in pr.REQUIREMENTS_BULLETS)
    assert any("скриншот" in b for b in pr.REJECT_BULLETS)
