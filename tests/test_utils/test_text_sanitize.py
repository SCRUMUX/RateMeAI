"""Unit tests for src.utils.text_sanitize.

LLM answers sometimes leak HTML tags, markdown fences, JSON keys or
control characters. The sanitizer must always produce plain Russian
prose safe to show in the web UI and in Telegram messages.
"""
from __future__ import annotations

import pytest

from src.utils.text_sanitize import sanitize_llm_text


@pytest.mark.parametrize(
    "raw,must_contain,must_not_contain",
    [
        (
            '<span style="color:red">Хороший кадр</span>',
            "Хороший кадр",
            "<span",
        ),
        (
            '```json\n{"first_impression": "Уверенный взгляд"}\n```',
            "Уверенный взгляд",
            "```",
        ),
        (
            '"first_impression": "Тёплое, живое фото"',
            "Тёплое, живое фото",
            '"first_impression"',
        ),
        (
            "Обычное сообщение без тегов",
            "Обычное сообщение без тегов",
            "<",
        ),
        (
            "Линия с `кодом` внутри",
            "Линия с кодом внутри",
            "`",
        ),
        (
            "Очень\x1b[31m цветной\x1b[0m текст",
            "Очень цветной текст",
            "\x1b",
        ),
    ],
)
def test_sanitize_strips_markup(raw: str, must_contain: str, must_not_contain: str) -> None:
    cleaned = sanitize_llm_text(raw)
    assert must_contain in cleaned
    assert must_not_contain not in cleaned


def test_sanitize_collapses_whitespace() -> None:
    out = sanitize_llm_text("a   b\t\t\tc\n\n\n\n\nd")
    assert "a b c" in out
    assert "\n\n\n" not in out


def test_sanitize_handles_none_and_non_string() -> None:
    assert sanitize_llm_text(None) == ""
    assert sanitize_llm_text("") == ""
    assert sanitize_llm_text(123) == "123"


def test_sanitize_respects_max_len() -> None:
    long = "x" * 5000
    out = sanitize_llm_text(long, max_len=100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_sanitize_decodes_entities() -> None:
    out = sanitize_llm_text("5&nbsp;минут &amp; 10&nbsp;секунд")
    assert "&nbsp;" not in out
    assert "&amp;" not in out
    assert "минут" in out
    assert "секунд" in out
