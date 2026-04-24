"""Variation Engine for handling user inputs and style variations.

v1.26 — ``allowed_variations`` is now a per-channel dict
(``{"lighting": [...], "scene": [...], "clothing": [...], "framing": [...]}``)
живущий в :class:`StructuredStyleSpec`. Раньше он был плоским списком, и
из-за этого:

- валидация выбирала из «ядрёной смеси» допустимых значений: для стиля
  «Эйфелева башня» мы не могли отличить допустимое ``lighting`` от
  недопустимого ``scene_override`` — всё лежало в одной куче;
- на фронте модалка «Другой вариант» рисовала одинаковый набор полей
  для всех стилей, вне зависимости от того, разрешает ли стиль менять
  сцену / одежду / освещение.

Теперь ``apply_variation`` валидирует каждое пользовательское поле по
своему каналу и применяет только те, которые стиль действительно
допускает. ``scene_override`` / ``clothing_override`` уважают тип стиля
(scene-locked / semi-locked / flexible) и наличие соответствующего
канала в ``allowed_variations``.
"""

from typing import Any
import random

from src.prompts.style_spec import StructuredStyleSpec, StyleType


_ALL_CHANNELS = ("lighting", "scene", "clothing", "framing")


def _is_allowed(
    spec: StructuredStyleSpec, channel: str, value: str
) -> bool:
    """Return True iff the style whitelists ``value`` on ``channel``."""
    options = (spec.allowed_variations or {}).get(channel) or []
    return isinstance(value, str) and value in options


def _channel_any(spec: StructuredStyleSpec, channel: str) -> bool:
    """Return True iff the style exposes the given channel at all."""
    return bool((spec.allowed_variations or {}).get(channel))


class VariationEngine:
    """Apply user-provided hints to a :class:`StructuredStyleSpec`.

    Output — готовая «сцена + одежда» строка для включения в промпт; всё,
    что не вписывается в per-style контракт, игнорируется (не
    перезатирает дефолт стиля).
    """

    @staticmethod
    def apply_variation(
        spec: StructuredStyleSpec,
        user_input: dict[str, Any] | None,
        *,
        strict: bool = True,
    ) -> str:
        """Compose «сцена + свет + одежда» string for the prompt.

        Args:
            spec: стиль, задающий базовые дефолты + ``allowed_variations``.
            user_input: пользовательские hints из «Другой вариант» (lighting /
                scene_override / clothing_override / weather / sub_location).
            strict: если ``True`` (default) — валидируем каждое поле по
                per-channel whitelist. Если ``False`` — доверяем caller-у и
                применяем значения как есть (используется, когда hints
                пришли из curated ``StyleVariant``, уже пропущенного через
                ревью автора стиля).
        """
        user_input = dict(user_input or {})

        scene = spec.base_scene or spec.scene or ""
        clothing = spec.clothing or ""

        lighting_value = str(user_input.get("lighting") or "").strip()
        weather_value = str(user_input.get("weather") or "").strip()
        sub_location_value = str(user_input.get("sub_location") or "").strip()
        scene_override = str(user_input.get("scene_override") or "").strip()
        clothing_override = str(user_input.get("clothing_override") or "").strip()

        def _ok(channel: str, value: str) -> bool:
            if not value:
                return False
            if not strict:
                return True
            return _is_allowed(spec, channel, value)

        lighting_line = f"{lighting_value} lighting" if _ok("lighting", lighting_value) else ""
        weather_line = f"{weather_value} weather" if _ok("lighting", weather_value) else ""

        if spec.type == StyleType.SCENE_LOCKED:
            # Scene-locked стили нельзя переопределять (Эйфелева башня
            # должна оставаться Эйфелевой башней) — только свет/погода.
            pass
        elif spec.type == StyleType.SEMI_LOCKED:
            allow_sub = (not strict) or _is_allowed(spec, "scene", sub_location_value)
            if sub_location_value and allow_sub:
                scene = f"{sub_location_value} in {scene}"
        elif spec.type == StyleType.FLEXIBLE:
            allow_scene = (not strict) or _channel_any(spec, "scene")
            if scene_override and allow_scene:
                scene = scene_override

        allow_clothing = (not strict) or _channel_any(spec, "clothing")
        if clothing_override and allow_clothing:
            clothing = clothing_override

        parts: list[str] = []
        if scene:
            parts.append(scene)
        if lighting_line:
            parts.append(lighting_line)
        if weather_line:
            parts.append(weather_line)

        scene_text = ", ".join(p.strip() for p in parts if p and p.strip())
        if clothing:
            return f"{scene_text}. Subject is wearing {clothing}."
        return f"{scene_text}."

    @staticmethod
    def get_random_variation(spec: StructuredStyleSpec) -> dict[str, str]:
        """Pick a random allowed variation for the 'Другой вариант' button.

        Собираем значения со всех каналов в один пул, выбираем 1–2 и
        отдаём как подсказку промпт-билдеру.
        """
        pool: list[str] = []
        for channel in _ALL_CHANNELS:
            options = (spec.allowed_variations or {}).get(channel) or []
            pool.extend(str(x) for x in options if isinstance(x, str) and x)

        if not pool:
            return {}

        num_vars = random.randint(1, min(2, len(pool)))
        chosen = random.sample(pool, num_vars)
        return {"variation_hints": ", ".join(chosen)}
