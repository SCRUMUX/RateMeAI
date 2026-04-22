"""Structural invariants for analysis / emoji prompts.

Phase 3 of the prompts-audit cleanup. We do not snapshot the full text —
we assert that the shared perception block is reused across all four
analysis modes, that the emoji prompt no longer ships with literal
ellipsis placeholders, and that the emoji image prompt preserves
identity and accepts gender.
"""
from __future__ import annotations

from src.prompts import rating, cv, social, dating, emoji
from src.prompts import image_gen as ig
from src.prompts.perception import (
    PERCEPTION_SCORING_FIELDS,
    PERCEPTION_SCORING_RULES,
)


def _marker() -> str:
    """A short, distinctive fragment from the shared perception block."""
    return '"warmth":'


def test_rating_uses_shared_perception_block():
    p = rating.build_prompt({})
    assert _marker() in p
    assert PERCEPTION_SCORING_FIELDS.strip()[:40] in p


def test_dating_uses_shared_perception_block():
    p = dating.build_prompt({})
    assert _marker() in p


def test_social_uses_shared_perception_block():
    p = social.build_prompt({})
    assert _marker() in p


def test_cv_uses_shared_perception_block():
    p = cv.build_prompt({"profession": "IT"})
    assert _marker() in p
    assert "perception_insights" in p


def test_cv_prompt_contains_profession_and_rounding_rules():
    p = cv.build_prompt({"profession": "дизайнер"})
    assert "дизайнер" in p
    assert "Округляй значения до сотых" in p


def test_perception_rules_have_updated_rounding_guidance():
    assert "Округляй значения до сотых" in PERCEPTION_SCORING_RULES
    assert "ровно 9.00" in PERCEPTION_SCORING_RULES


def test_perception_rules_dont_ban_neutral_words():
    """«отведен», «неуверенный», «закрытый» are neutral descriptions
    and must not be globally banned — they can legitimately appear in
    suggestions."""
    for word in ("отведен", "неуверенный", "закрытый"):
        assert f'"{word}"' not in PERCEPTION_SCORING_RULES
        assert f"«{word}»" not in PERCEPTION_SCORING_RULES


def test_rating_tone_is_reframed():
    p = rating.build_prompt({})
    assert "слегка провокационный" not in p
    assert "с лёгким ироничным акцентом" in p


def test_emoji_prompt_has_no_triple_dots():
    """The sticker-list placeholders must be full, not '...'."""
    p = emoji.build_prompt({})
    lines = [line for line in p.splitlines() if '"description"' in line]
    assert len(lines) == 12
    for line in lines:
        assert '"..."' not in line, f"triple-dot leak in emoji prompt: {line}"


def test_emoji_prompt_has_all_12_emotions():
    p = emoji.build_prompt({})
    for emotion in (
        "happy", "sad", "angry", "surprised", "love", "cool",
        "thinking", "laughing", "sleepy", "wink", "scared", "party",
    ):
        assert f'"{emotion}"' in p


def test_emoji_image_prompt_preserves_identity():
    p = ig.build_emoji_prompt("", gender="male")
    assert "maintaining exact facial proportions" in p
    assert "instantly recognizable as the same person" in p


def test_emoji_image_prompt_has_no_legacy_reve_syntax():
    p = ig.build_emoji_prompt("")
    assert "<ref>" not in p
    assert "</ref>" not in p


def test_emoji_image_prompt_accepts_gender():
    male = ig.build_emoji_prompt("", gender="male")
    female = ig.build_emoji_prompt("", gender="female")
    empty = ig.build_emoji_prompt("")
    assert "Male character" in male
    assert "Female character" in female
    assert "Male character" not in empty
    assert "Female character" not in empty
