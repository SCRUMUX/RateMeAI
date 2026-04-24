"""Parity tests: StyleSpecV2 path matches v1 output for equivalent data.

PR1 of the style-schema-v2 migration. The plan requires that
``PromptEngine.build_image_prompt_v2`` produces a prompt that matches
the v1 output byte-for-byte for neutral inputs (no framing, no
weather, no variant) when the underlying style's v2 spec is a
mechanical mirror of the v1 StructuredStyleSpec.

Three dimensions covered:

1. Flag-off parity: enabling ``style_schema_v2_enabled`` **without**
   migrating any JSON entry must not change any production prompt.
2. Neutral-input parity: for dating / cv / social sample styles the
   v2 path matches v1 byte-for-byte when no framing / weather / hints
   are supplied.
3. Framing parity: framing directive propagates identically.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts import image_gen as ig
from src.prompts.engine import PromptEngine
from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    BackgroundSlot,
    ClothingSlot,
    QualityBlock,
    StyleSpecV2,
    WeatherPolicy,
)
from src.prompts.image_gen import STYLE_REGISTRY  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_v2_registry():
    """Each test starts with a clean v2 registry to avoid bleed-through."""
    snapshot = dict(STYLE_REGISTRY._v2_by_key)
    STYLE_REGISTRY._v2_by_key.clear()
    yield
    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot)


def _mirror_v1_as_v2(mode: str, key: str) -> StyleSpecV2:
    """Build a v2 spec from an already-registered v1 StructuredStyleSpec.

    All fields are copied across so the wrapper output must be
    bit-for-bit identical to the v1 ``_build_mode_prompt`` result.
    Weather is disabled (the v1 specs for JSON styles never populate
    it) and per-model tail is left empty so the default common tail
    is used.
    """
    v1 = STYLE_REGISTRY.get(mode, key)
    assert v1 is not None, f"v1 spec missing: {mode}/{key}"

    allowed = getattr(v1, "allowed_variations", None) or {}

    context_slots = {
        "lighting": tuple(allowed.get("lighting", ())),
        "angle_placement": tuple(allowed.get("angle_placement", ())),
        "framing": tuple(
            allowed.get("framing", ("portrait", "half_body", "full_body"))
        ),
    }

    from src.prompts.style_spec import StyleType

    v1_type = getattr(v1, "type", StyleType.FLEXIBLE)
    lock = {
        StyleType.SCENE_LOCKED: BackgroundLockLevel.LOCKED,
        StyleType.SEMI_LOCKED: BackgroundLockLevel.SEMI,
        StyleType.FLEXIBLE: BackgroundLockLevel.FLEXIBLE,
    }.get(v1_type, BackgroundLockLevel.FLEXIBLE)

    return StyleSpecV2(
        key=key,
        mode=mode,
        trigger="",
        background=BackgroundSlot(
            base=getattr(v1, "base_scene", "") or getattr(v1, "scene", ""),
            lock=lock,
            overrides_allowed=tuple(allowed.get("scene", ())),
        ),
        clothing=ClothingSlot(
            default=getattr(v1, "clothing", "") or "",
            allowed=tuple(allowed.get("clothing", ())),
        ),
        weather=WeatherPolicy(enabled=False, allowed=(), default_na=True),
        context_slots=context_slots,
        quality_identity=QualityBlock(base="", per_model_tail={}),
        expression=getattr(v1, "expression", "") or "",
        needs_full_body=bool(getattr(v1, "needs_full_body", False)),
    )


# ---------------------------------------------------------------------------
# 1) Flag on, no v2 migration = zero prompts change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,style",
    [
        ("dating", "warm_outdoor"),
        ("dating", "rooftop_city"),
        ("cv", "corporate"),
        ("social", "influencer"),
    ],
)
def test_flag_on_without_v2_migration_preserves_v1_output(
    monkeypatch, mode, style
):
    """The most important parity test. If this ever fails, we broke
    additivity and must block the PR."""
    monkeypatch.setattr(settings, "unified_prompt_v2_enabled", True, raising=False)
    STYLE_REGISTRY._v2_by_key.clear()

    mode_enum = {
        "dating": AnalysisMode.DATING,
        "cv": AnalysisMode.CV,
        "social": AnalysisMode.SOCIAL,
    }[mode]

    engine = PromptEngine()
    via_engine = engine.build_image_prompt(
        mode=mode_enum,
        style=style,
        gender="male",
        framing="half_body",
        target_model="gpt_image_2",
    )

    v2_output = engine.build_image_prompt_v2(
        mode=mode_enum,
        style=style,
        gender="male",
        framing="half_body",
        target_model="gpt_image_2",
    )
    assert v2_output is None, (
        "v2 builder returned a prompt for an un-migrated style; "
        "executor branching would silently switch paths. "
        f"got: {v2_output!r}"
    )
    assert via_engine, "v1 path produced empty prompt"


# ---------------------------------------------------------------------------
# 2) Neutral-input parity for a mirrored v2 spec
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,style",
    [
        ("dating", "warm_outdoor"),
        ("cv", "corporate"),
        ("social", "influencer"),
    ],
)
def test_v2_matches_v1_for_neutral_inputs(monkeypatch, mode, style):
    """When the v2 spec mirrors the v1 spec, and the caller does not
    pass weather / framing / variant, ``build_image_prompt_v2`` must
    match the direct-builder output byte-for-byte.
    """
    v2 = _mirror_v1_as_v2(mode, style)
    STYLE_REGISTRY.register_v2(v2)

    mode_enum = {
        "dating": AnalysisMode.DATING,
        "cv": AnalysisMode.CV,
        "social": AnalysisMode.SOCIAL,
    }[mode]
    builder = {
        "dating": ig.build_dating_prompt,
        "cv": ig.build_cv_prompt,
        "social": ig.build_social_prompt,
    }[mode]

    engine = PromptEngine()
    via_v2 = engine.build_image_prompt_v2(
        mode=mode_enum,
        style=style,
        gender="male",
        target_model="gpt_image_2",
    )
    via_v1 = builder(
        style=style,
        base_description="",
        gender="male",
        input_hints=None,
        variant=None,
        target_model="gpt_image_2",
        framing=None,
    )
    assert via_v2 == via_v1, (
        f"\n--- v2 ---\n{via_v2}\n--- v1 ---\n{via_v1}\n"
    )


# ---------------------------------------------------------------------------
# 3) Framing parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_v2_framing_parity(monkeypatch, framing):
    v2 = _mirror_v1_as_v2("dating", "warm_outdoor")
    STYLE_REGISTRY.register_v2(v2)

    engine = PromptEngine()
    via_v2 = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        gender="male",
        framing=framing,
        target_model="gpt_image_2",
    )
    via_v1 = ig.build_dating_prompt(
        style="warm_outdoor",
        base_description="",
        gender="male",
        input_hints=None,
        variant=None,
        target_model="gpt_image_2",
        framing=framing,
    )
    assert via_v2 == via_v1


# ---------------------------------------------------------------------------
# 4) Per-model tail plumbing — with per_model_tail set, the outputs
#    for gpt_image_2 and nano_banana_2 differ only in the tail
# ---------------------------------------------------------------------------


def test_per_model_tail_changes_tail_only(monkeypatch):
    v2 = _mirror_v1_as_v2("dating", "warm_outdoor")
    v2 = StyleSpecV2(
        **{
            **v2.__dict__,
            "quality_identity": QualityBlock(
                base="",
                per_model_tail={
                    "gpt_image_2": "Custom GPT tail.",
                    "nano_banana_2": "Custom Nano tail.",
                },
            ),
        }
    )
    STYLE_REGISTRY.register_v2(v2)

    engine = PromptEngine()
    p_gpt = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        gender="male",
        target_model="gpt_image_2",
    )
    p_nano = engine.build_image_prompt_v2(
        mode=AnalysisMode.DATING,
        style="warm_outdoor",
        gender="male",
        target_model="nano_banana_2",
    )
    assert p_gpt.endswith("Custom GPT tail.")
    assert p_nano.endswith("Custom Nano tail.")
    # Everything before the tail must be identical
    p_gpt_body = p_gpt[: -len("Custom GPT tail.")]
    p_nano_body = p_nano[: -len("Custom Nano tail.")]
    assert p_gpt_body == p_nano_body


# ---------------------------------------------------------------------------
# 5) Loader round-trip: parsing a v2 JSON dict yields a usable spec
# ---------------------------------------------------------------------------


def test_style_loader_v2_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "style_schema_v2_enabled", True, raising=False)
    from src.services.style_loader_v2 import register_v2_styles_from_json

    raw = [
        {
            "id": "warm_outdoor",
            "mode": "dating",
            "schema_version": 2,
            "trigger": "park",
            "background": {
                "base": "golden-hour park, warm backlight",
                "lock": "flexible",
                "overrides_allowed": ["beach"],
            },
            "clothing": {
                "default": "crew-neck tee and chinos",
                "allowed": ["denim jacket"],
                "gender_neutral": True,
            },
            "weather": {
                "enabled": True,
                "allowed": ["clear", "overcast"],
                "default_na": False,
            },
            "context_slots": {
                "lighting": ["golden", "soft"],
                "framing": ["portrait", "half_body", "full_body"],
            },
            "quality_identity": {
                "base": "",
                "per_model_tail": {"gpt_image_2": "GPT-specific."},
            },
            "expression": "Relaxed warm smile.",
        }
    ]

    registered = register_v2_styles_from_json(raw)
    assert registered == 1
    spec = STYLE_REGISTRY.get_v2("dating", "warm_outdoor")
    assert spec is not None
    assert spec.weather.enabled is True
    assert "clear" in spec.weather.allowed
    assert spec.clothing.default == "crew-neck tee and chinos"
    assert spec.background.lock == BackgroundLockLevel.FLEXIBLE
    assert spec.quality_identity.per_model_tail["gpt_image_2"] == "GPT-specific."


def test_style_loader_v2_flag_off_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "style_schema_v2_enabled", False, raising=False)
    from src.services.style_loader_v2 import register_v2_styles_from_json

    raw = [
        {
            "id": "warm_outdoor",
            "mode": "dating",
            "schema_version": 2,
            "background": {"base": "park", "lock": "flexible"},
            "clothing": {"default": "tee"},
        }
    ]
    STYLE_REGISTRY._v2_by_key.clear()
    registered = register_v2_styles_from_json(raw)
    assert registered == 0
    assert STYLE_REGISTRY.get_v2("dating", "warm_outdoor") is None


def test_style_loader_v2_skips_v1_entries(monkeypatch):
    """v1-only entries (no schema_version) must not be picked up by v2 loader."""
    monkeypatch.setattr(settings, "style_schema_v2_enabled", True, raising=False)
    from src.services.style_loader_v2 import register_v2_styles_from_json

    raw = [
        {"id": "legacy_style", "mode": "dating", "base_scene": "park"},
        {"id": "legacy_cv", "mode": "cv", "schema_version": 1},
    ]
    STYLE_REGISTRY._v2_by_key.clear()
    registered = register_v2_styles_from_json(raw)
    assert registered == 0
