"""Phase 2 (v1.27.3): gender-aware ``ClothingSlot.default``.

The slot now carries a ``{male, female, neutral}`` dict. We verify:

* ``StyleSpecV2.clothing_for(gender)`` returns the gender-specific
  string when present.
* ``clothing_for`` falls back to ``neutral`` when the requested gender
  is missing or empty, then to the first non-empty value.
* The composition builder threads ``gender`` through and the rendered
  prompt actually differs for male / female on a curated gendered
  style (Burj Khalifa).
* Strings authored equal across all three keys yield identical prompts
  regardless of gender (back-compat for non-gendered styles).
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY
from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    BackgroundSlot,
    ClothingSlot,
    QualityBlock,
    StyleSpecV2,
    WeatherPolicy,
)
from src.services.style_loader import load_styles_from_json
from src.services.style_loader_v2 import register_v2_styles_from_json


@pytest.fixture
def _v2_registered(monkeypatch):
    monkeypatch.setattr(settings, "style_schema_v2_enabled", True, raising=False)
    monkeypatch.setattr(settings, "unified_prompt_v2_enabled", True, raising=False)
    snapshot = dict(STYLE_REGISTRY._v2_by_key)
    STYLE_REGISTRY._v2_by_key.clear()
    register_v2_styles_from_json(load_styles_from_json())
    yield
    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot)


def _mk_spec(default: object, *, key: str = "test_style", mode: str = "dating") -> StyleSpecV2:
    return StyleSpecV2(
        key=key,
        mode=mode,
        trigger="",
        background=BackgroundSlot(base="rooftop", lock=BackgroundLockLevel.FLEXIBLE),
        clothing=ClothingSlot(default=default),  # type: ignore[arg-type]
        weather=WeatherPolicy(),
        context_slots={},
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


def test_clothing_for_returns_gender_specific_value():
    spec = _mk_spec({"male": "M", "female": "F", "neutral": "N"})
    assert spec.clothing_for("male") == "M"
    assert spec.clothing_for("female") == "F"
    assert spec.clothing_for("neutral") == "N"


def test_clothing_for_falls_back_to_neutral_when_gender_blank():
    spec = _mk_spec({"male": "", "female": "", "neutral": "N"})
    assert spec.clothing_for("male") == "N"
    assert spec.clothing_for("female") == "N"


def test_clothing_for_falls_back_to_first_nonempty_when_neutral_blank():
    spec = _mk_spec({"male": "M", "female": "", "neutral": ""})
    assert spec.clothing_for("female") == "M"


def test_clothing_for_accepts_legacy_string_default():
    """Pre-1.27.3 specs may still pass a plain string. The
    ``ClothingSlot.text`` helper must treat it as a single neutral
    fallback so historic callers do not crash mid-loader."""
    spec = _mk_spec("crew-neck tee and chinos")
    assert spec.clothing_for("male") == "crew-neck tee and chinos"
    assert spec.clothing_for("female") == "crew-neck tee and chinos"


def test_burj_khalifa_male_and_female_prompts_differ(_v2_registered):
    """Burj Khalifa is in the hand-curated FEMALE_OVERRIDES list. The
    rendered prompt must reflect the gender override and not just the
    male phrasing for female users."""
    engine = PromptEngine()
    male_prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="dubai_burj_khalifa",
        gender="male",
        target_model="gpt_image_2",
    )
    female_prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="dubai_burj_khalifa",
        gender="female",
        target_model="gpt_image_2",
    )
    assert male_prompt and female_prompt
    assert male_prompt != female_prompt, (
        "Gender-aware clothing should produce different prompts for "
        "male and female on Burj Khalifa."
    )
    assert "fitted dark shirt" in male_prompt.lower()
    # The hand-curated female variant explicitly mentions either dress or pencil skirt.
    assert any(
        token in female_prompt.lower()
        for token in ("dress", "pencil skirt", "blouse")
    )


def test_non_gendered_style_yields_identical_prompts(_v2_registered):
    """A style whose clothing.default has the same value for male and
    female (e.g. ``london_eye``) must produce byte-identical prompts
    for both genders so the back-compat path stays loss-less."""
    engine = PromptEngine()
    male_prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="london_eye",
        gender="male",
        target_model="gpt_image_2",
    )
    female_prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="london_eye",
        gender="female",
        target_model="gpt_image_2",
    )
    assert male_prompt and female_prompt
    assert male_prompt == female_prompt
