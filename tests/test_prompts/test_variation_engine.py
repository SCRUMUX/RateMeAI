"""v1.26 — VariationEngine per-channel ``allowed_variations`` validation.

``StructuredStyleSpec.allowed_variations`` теперь ``dict[str, list[str]]``
(каналы: ``lighting``, ``scene``, ``clothing``, ``framing``). Эти тесты
фиксируют контракт:

* пустой канал = фича выключена для стиля; hint игнорируется;
* непустой канал = hint должен лежать в whitelist'е, иначе дефолт
  стиля сохраняется;
* ``strict=False`` пропускает любой ненулевой hint (используется для
  curated ``StyleVariant``, уже прошедшего авторский ревью);
* одежда переопределяется только если стиль вообще экспонирует канал
  ``clothing`` — отдельный стоп-тумблер от «Эйфелевой башни».
"""

from __future__ import annotations

from src.prompts.style_spec import StructuredStyleSpec, StyleType
from src.prompts.variation_engine import VariationEngine


def _make_spec(
    *,
    type_: StyleType = StyleType.FLEXIBLE,
    allowed: dict[str, list[str]] | None = None,
    base_scene: str = "city rooftop at dusk",
    clothing: str = "charcoal crewneck sweater",
) -> StructuredStyleSpec:
    return StructuredStyleSpec(
        name="test_style",
        type=type_,
        base_scene=base_scene,
        allowed_variations=allowed or {},
        camera="35mm",
        pose="relaxed",
        clothing=clothing,
        scene=base_scene,
        lighting="soft ambient",
        weather="",
        emotion="confident",
        energy="calm",
        photo_style="editorial",
        expression="",
    )


def test_lighting_hint_applied_when_whitelisted():
    spec = _make_spec(
        allowed={"lighting": ["golden hour", "overcast"], "scene": [], "clothing": []}
    )
    text = VariationEngine.apply_variation(spec, {"lighting": "golden hour"})
    assert "golden hour lighting" in text


def test_lighting_hint_rejected_when_not_whitelisted():
    spec = _make_spec(
        allowed={"lighting": ["golden hour"], "scene": [], "clothing": []}
    )
    text = VariationEngine.apply_variation(spec, {"lighting": "studio flash"})
    assert "studio flash" not in text.lower()


def test_scene_override_only_for_flexible_with_scene_channel():
    """Для FLEXIBLE-стиля ``scene_override`` применяется только если
    whitelist непустой. Иначе дефолтная сцена стиля остаётся как есть
    — такой контракт страхует от «подделки жанра» через модалку."""
    spec_open = _make_spec(
        type_=StyleType.FLEXIBLE,
        allowed={"scene": ["coastal cliff"], "lighting": [], "clothing": []},
    )
    out_open = VariationEngine.apply_variation(
        spec_open, {"scene_override": "snowy mountain peak"}
    )
    assert "snowy mountain peak" in out_open

    spec_closed = _make_spec(
        type_=StyleType.FLEXIBLE,
        allowed={"scene": [], "lighting": [], "clothing": []},
    )
    out_closed = VariationEngine.apply_variation(
        spec_closed, {"scene_override": "snowy mountain peak"}
    )
    assert "snowy mountain peak" not in out_closed
    assert spec_closed.base_scene in out_closed


def test_scene_locked_style_ignores_scene_override():
    """«Эйфелева башня» = ``SCENE_LOCKED``: даже если ``scene`` в
    whitelist'е случайно непустой, сцену нельзя перезаписать. Меняется
    только свет / погода."""
    spec = _make_spec(
        type_=StyleType.SCENE_LOCKED,
        base_scene="Paris, Eiffel Tower at dusk",
        allowed={
            "lighting": ["golden hour", "blue hour"],
            "scene": ["coastal cliff"],
            "clothing": [],
        },
    )
    text = VariationEngine.apply_variation(
        spec, {"scene_override": "coastal cliff", "lighting": "blue hour"}
    )
    assert "Paris, Eiffel Tower" in text
    assert "coastal cliff" not in text
    assert "blue hour lighting" in text


def test_clothing_override_blocked_when_channel_empty():
    """Clothing канал как kill-switch: если стиль объявил
    ``"clothing": []``, пользовательский ``clothing_override`` ломает
    дефолт стиля — это запрещено."""
    spec = _make_spec(
        allowed={"lighting": [], "scene": [], "clothing": []},
        clothing="navy blazer",
    )
    out = VariationEngine.apply_variation(
        spec, {"clothing_override": "red leather jacket"}
    )
    assert "navy blazer" in out
    assert "red leather jacket" not in out


def test_clothing_override_applies_when_channel_exposed():
    spec = _make_spec(
        allowed={"lighting": [], "scene": [], "clothing": ["*"]},
        clothing="navy blazer",
    )
    out = VariationEngine.apply_variation(
        spec, {"clothing_override": "red leather jacket"}
    )
    assert "red leather jacket" in out


def test_strict_false_trusts_curated_values():
    """Для curated StyleVariant значения уже прошли автор-ревью, поэтому
    ``strict=False`` применяет их без валидации. Это позволяет ротацию
    «Другой вариант» не ломаться, когда autor подлил экзотический
    lighting, которого нет в whitelist для UI."""
    spec = _make_spec(
        allowed={"lighting": ["golden hour"], "scene": [], "clothing": []}
    )
    out = VariationEngine.apply_variation(
        spec, {"lighting": "neon cyan"}, strict=False
    )
    assert "neon cyan lighting" in out


def test_get_random_variation_pools_across_channels():
    """``get_random_variation`` собирает значения со всех каналов в один
    пул и возвращает подсказку. Если все каналы пусты — отдаёт {}."""
    spec_empty = _make_spec(
        allowed={"lighting": [], "scene": [], "clothing": [], "framing": []}
    )
    assert VariationEngine.get_random_variation(spec_empty) == {}

    spec = _make_spec(
        allowed={
            "lighting": ["golden hour"],
            "scene": [],
            "clothing": [],
            "framing": ["portrait"],
        }
    )
    out = VariationEngine.get_random_variation(spec)
    assert "variation_hints" in out
    hints = out["variation_hints"].split(", ")
    for h in hints:
        assert h in {"golden hour", "portrait"}
