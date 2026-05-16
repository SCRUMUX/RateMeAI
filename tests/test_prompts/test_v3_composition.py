"""Stage 1 (prompt-pipeline-overhaul): v3 composition builder + engine
wiring tests.

These tests verify three integration contracts:

1. :func:`build_composition_v3` produces a CompositionIR whose
   ``scene`` always contains the rolled trigger — the inviolable
   axis of the v3 schema.
2. ``CompositionIR.scene_line()`` doesn't introduce the "X lighting
   lighting" stutter when the v3 sampler hands it values that are
   already pure adjectives.
3. :meth:`PromptEngine.build_image_prompt_v2` prefers v3 specs when
   the feature flag is on and a v3 spec is registered, AND it falls
   back to v2 when v3 is absent.

We deliberately test through the public engine API (not the low-level
builder) for the wiring assertion — that is the exact path the
executor takes.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.composition_builder import build_composition_v3
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
from src.prompts.style_schema_v3 import (
    AmbientPools,
    StyleSpecV3,
)


def _v3(
    *,
    key: str = "burj_khalifa",
    mode: str = "social",
    trigger_pool: tuple[str, ...] = (
        "Burj Khalifa skyline at twilight",
        "Burj Khalifa lit at night",
        "rooftop with the Burj Khalifa silhouette",
    ),
    scene_anchor: str = "open-air observation terrace overlooking Dubai",
    lighting: tuple[str, ...] = ("warm cinematic", "soft golden", "blue hour"),
) -> StyleSpecV3:
    return StyleSpecV3(
        key=key,
        mode=mode,
        trigger_pool=trigger_pool,
        scene_anchor=scene_anchor,
        ambient=AmbientPools(lighting=lighting),
        clothing=ClothingSlot(
            default={"male": "suit", "female": "dress", "neutral": "smart casual"},
            allowed=(),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


def _v2(*, key: str = "burj_khalifa", mode: str = "social") -> StyleSpecV2:
    return StyleSpecV2(
        key=key,
        mode=mode,
        trigger="Burj Khalifa",
        background=BackgroundSlot(
            base="Dubai skyline view",
            lock=BackgroundLockLevel.SEMI,
            overrides_allowed=(),
        ),
        clothing=ClothingSlot(
            default={"male": "suit", "female": "dress", "neutral": "smart"},
            allowed=(),
        ),
        weather=WeatherPolicy(enabled=False, allowed=(), default_na=True),
        context_slots={},
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


# ---------- build_composition_v3 ------------------------------------------


def test_build_composition_v3_always_emits_trigger_in_scene():
    spec = _v3()
    for s in range(20):
        ir = build_composition_v3(
            spec,
            mode="social",
            change_instruction="Change.",
            input_hints={},
            seed=s,
        )
        assert any(t.lower() in ir.scene.lower() for t in spec.trigger_pool), (
            f"Seed {s}: scene {ir.scene!r} contains none of the trigger pool"
        )


def test_build_composition_v3_no_lighting_stutter_in_scene_line():
    spec = _v3(lighting=("warm tungsten light",))
    ir = build_composition_v3(
        spec,
        mode="social",
        change_instruction="Change.",
        input_hints={},
        seed=0,
    )
    line = ir.scene_line()
    assert "light lighting" not in line.lower()


def test_build_composition_v3_rejects_non_v3_spec():
    with pytest.raises(TypeError, match="StyleSpecV3"):
        build_composition_v3(
            _v2(),
            mode="social",
            change_instruction="Change.",
        )


def test_build_composition_v3_records_substitutions_for_off_pool_pin():
    spec = _v3(lighting=("warm cinematic", "soft golden"))
    ir = build_composition_v3(
        spec,
        mode="social",
        change_instruction="Change.",
        input_hints={"lighting": "neon"},
        seed=0,
        strict=True,
    )
    assert any(s["channel"] == "lighting" for s in ir.substitutions)


# ---------- engine wiring (v3 preferred when flag on) ----------------------


@pytest.fixture
def _registry_isolated():
    """Snapshot/restore the v2 + v3 maps so each test starts clean."""
    snap_v2 = dict(STYLE_REGISTRY._v2_by_key)
    snap_v3 = dict(STYLE_REGISTRY._v3_by_key)
    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()
    yield
    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snap_v2)
    STYLE_REGISTRY._v3_by_key.update(snap_v3)


def test_engine_prefers_v3_when_flag_on(monkeypatch, _registry_isolated):

    spec_v3 = _v3(key="z", mode="social")
    spec_v2 = _v2(key="z", mode="social")
    STYLE_REGISTRY.register_v3(spec_v3)
    STYLE_REGISTRY.register_v2(spec_v2)

    engine = PromptEngine()
    resolved: dict[str, object] = {}
    prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.SOCIAL,
        style="z",
        gender="male",
        input_hints={},
        target_model="gpt_image_2",
        seed=7,
        out_resolved_slots=resolved,
    )

    assert prompt
    # v3 path populates out_resolved_slots; v2 path doesn't touch it.
    assert resolved, "engine did not write out_resolved_slots — v2 path was used"
    assert any(t.lower() in prompt.lower() for t in spec_v3.trigger_pool)


def test_engine_falls_back_to_v2_when_v3_missing(
    monkeypatch, _registry_isolated
):

    STYLE_REGISTRY.register_v2(_v2(key="z", mode="social"))

    engine = PromptEngine()
    resolved: dict[str, object] = {}
    prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.SOCIAL,
        style="z",
        gender="male",
        input_hints={},
        target_model="gpt_image_2",
        seed=7,
        out_resolved_slots=resolved,
    )

    assert prompt
    # v2 path leaves out_resolved_slots untouched — that's how the
    # executor distinguishes the two paths.
    assert not resolved


def test_engine_returns_none_for_unknown_style(
    monkeypatch, _registry_isolated
):

    engine = PromptEngine()
    prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.SOCIAL,
        style="does_not_exist",
        gender="male",
        target_model="gpt_image_2",
    )
    assert prompt is None


# ---------- 1.32.0 e2e: full ResolvedSlots persistence + determinism ------


def _v3_with_full_pools(*, key: str = "e2e_test", mode: str = "social") -> StyleSpecV3:
    """v3 spec with every ambient channel populated, used to verify
    the engine forwards a full ResolvedSlots payload (not just the
    IR-flat subset) into ``out_resolved_slots``."""
    return StyleSpecV3(
        key=key,
        mode=mode,
        trigger_pool=("anchor formulation A", "anchor formulation B"),
        scene_anchor="canonical scene anchor",
        ambient=AmbientPools(
            lighting=("soft warm", "blue hour", "neutral overcast"),
            weather=("clear", "light overcast"),
            time_of_day=("morning", "evening"),
            season=("spring", "summer", "autumn", "winter"),
        ),
        clothing=ClothingSlot(
            default={"male": "smart casual", "female": "smart casual", "neutral": "smart casual"},
            allowed=("smart casual", "business formal"),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
    )


def test_engine_forwards_full_resolved_slots_payload(
    monkeypatch, _registry_isolated
):
    """1.32.0 — ``out_resolved_slots`` must contain the full set of
    fields that ``ResolvedSlots.to_dict()`` produces, not only the
    subset that the IR's flat fields preserve. UI badges depend on
    ``trigger`` / ``time_of_day`` / ``season`` / ``random_picks`` /
    ``user_overrides`` / ``substitutions``; before 1.32.0 those keys
    were silently dropped because trigger/time/season got baked into
    the flattened ``scene`` string.
    """

    STYLE_REGISTRY.register_v3(_v3_with_full_pools(key="z", mode="social"))

    engine = PromptEngine()
    resolved: dict[str, object] = {}
    prompt = engine.build_image_prompt_v2(
        mode=AnalysisMode.SOCIAL,
        style="z",
        gender="male",
        input_hints={},
        target_model="gpt_image_2",
        seed=42,
        out_resolved_slots=resolved,
    )

    assert prompt
    expected_keys = {
        "trigger",
        "scene",
        "lighting",
        "weather",
        "time_of_day",
        "season",
        "clothing",
        "expression",
        "random_picks",
        "user_overrides",
        "substitutions",
    }
    missing = expected_keys - resolved.keys()
    assert not missing, (
        f"resolved_slots is missing keys: {missing}. "
        f"Got: {sorted(resolved.keys())}"
    )
    # Concrete pulls from the v3 sampler — every ambient channel of
    # the spec has a non-empty pool, so we expect non-empty values.
    for ch in ("trigger", "lighting", "weather", "time_of_day", "season"):
        assert resolved[ch], f"channel {ch} was rolled empty"
    # No user input → all channels rolled randomly. random_picks
    # should cover every ambient channel; user_overrides should be
    # empty.
    random_picks = resolved["random_picks"]
    user_overrides = resolved["user_overrides"]
    assert isinstance(random_picks, dict)
    assert isinstance(user_overrides, dict)
    assert {"trigger", "lighting", "weather", "time_of_day", "season"} <= set(
        random_picks.keys()
    )
    assert user_overrides == {}


def test_engine_seeded_pipeline_is_deterministic(
    monkeypatch, _registry_isolated
):
    """Same ``(spec, hints, seed)`` triple must produce the same
    final prompt + resolved_slots on repeated runs. This is the
    contract that lets the executor replay a generation with the
    same inputs and expect the same model-facing string.
    """

    STYLE_REGISTRY.register_v3(_v3_with_full_pools(key="z", mode="social"))

    def _run(seed: int) -> tuple[str, dict[str, object]]:
        engine = PromptEngine()
        resolved: dict[str, object] = {}
        prompt = engine.build_image_prompt_v2(
            mode=AnalysisMode.SOCIAL,
            style="z",
            gender="male",
            input_hints={"clothing_override": "tweed jacket"},
            target_model="gpt_image_2",
            seed=seed,
            out_resolved_slots=resolved,
        )
        return prompt or "", resolved

    p1, r1 = _run(seed=99)
    p2, r2 = _run(seed=99)
    assert p1 == p2, "same seed produced different prompts"
    assert r1 == r2, "same seed produced different resolved_slots"

    p3, _ = _run(seed=100)
    assert p1 != p3, "different seeds produced identical prompts (sampler stuck?)"


def test_engine_user_overrides_partition_resolved_slots(
    monkeypatch, _registry_isolated
):
    """When the user pins a channel via ``input_hints`` and the value
    is in the pool, the sampler must put it in ``user_overrides`` and
    NOT in ``random_picks``. UI badges read this partition to render
    a different visual hint for "user-pinned" vs "rolled".
    """

    STYLE_REGISTRY.register_v3(_v3_with_full_pools(key="z", mode="social"))

    engine = PromptEngine()
    resolved: dict[str, object] = {}
    engine.build_image_prompt_v2(
        mode=AnalysisMode.SOCIAL,
        style="z",
        gender="male",
        input_hints={"lighting": "soft warm"},
        target_model="gpt_image_2",
        seed=1,
        out_resolved_slots=resolved,
    )

    user_overrides = resolved["user_overrides"]
    random_picks = resolved["random_picks"]
    assert isinstance(user_overrides, dict)
    assert isinstance(random_picks, dict)
    assert user_overrides.get("lighting") == "soft warm"
    assert "lighting" not in random_picks
