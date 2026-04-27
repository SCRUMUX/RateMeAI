"""Style schema v2 — slot-based, model-aware, version-tagged.

PR1 of the style-schema-v2 migration. This module is additive: the v1
``StructuredStyleSpec`` / ``StyleSpec`` types in
:mod:`src.prompts.style_spec` continue to power production. A JSON entry
in ``data/styles.json`` opts into the v2 path by setting
``"schema_version": 2`` — otherwise the v1 loader handles it and this
module is never consulted.

Design goals (per plan):

- Trigger as a first-class anchor ("gym", "rooftop", "cafe"), separate
  from the free-form base scene description.
- Context slots — whitelist-style dicts for the channels the user can
  override from the "Другой вариант" modal: ``angle_placement``,
  ``framing``, ``lighting``. Empty list = channel closed for this style.
- Weather as its own policy block (not piggy-backing on ``lighting``),
  with an explicit ``default_na`` so the renderer knows to emit "N/A"
  or simply drop the channel.
- Clothing + background as dedicated slots with lock-levels.
- Quality / identity as a separate block with an optional per-model
  tail, so we can tune Nano Banana 2 and GPT Image 2 independently
  without forking the scene description.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


SCHEMA_VERSION = 2


class BackgroundLockLevel(str, Enum):
    """How freely the user may override the background.

    Mirrors :class:`src.prompts.style_spec.StyleType` so v1 and v2 can
    coexist in the registry without surprising the router.
    """

    LOCKED = "locked"
    SEMI = "semi"
    FLEXIBLE = "flexible"


@dataclass(frozen=True)
class WeatherPolicy:
    """Declarative weather slot.

    Attributes:
        enabled: True = the scene is weather-sensitive (e.g. outdoor
            park) and a weather value may be injected into the prompt.
        allowed: whitelist of accepted values for ``input_hints["weather"]``.
        default_na: when True and no user value is set, the wrapper may
            emit nothing (scene ignores weather) instead of a neutral
            default. Documents and closed studios use ``default_na=True``.
    """

    enabled: bool = False
    allowed: tuple[str, ...] = ()
    default_na: bool = True


@dataclass(frozen=True)
class ClothingSlot:
    """Clothing slot for a v2 style.

    ``default`` is a per-gender dict ``{"male": ..., "female": ...,
    "neutral": ...}``. Empty keys fall back to ``neutral`` so a style
    that doesn't differentiate genders just sets ``neutral`` and stays
    silent on ``male`` / ``female``. The legacy ``str`` form is still
    accepted by the loader (it materialises as
    ``{"male": s, "female": s, "neutral": s}``) so migrations can ship
    incrementally.

    ``allowed`` is the whitelist consulted when
    ``input_hints["clothing_override"]`` is set. ``gender_neutral=True``
    is a hint for the admin UI / catalog: when the JSON declares a
    style as gender-neutral, the modal can hide per-gender editors.
    """

    default: dict[str, str] = field(default_factory=dict)
    allowed: tuple[str, ...] = ()
    gender_neutral: bool = True

    def text(self, gender: str = "neutral") -> str:
        """Return the clothing line for ``gender`` with sane fallbacks.

        Order: requested gender → ``neutral`` → first non-empty value
        → empty string. Returns ``""`` only when every key is blank.
        """
        if not isinstance(self.default, dict):
            return str(self.default or "")
        key = (gender or "").strip().lower()
        if key not in {"male", "female", "neutral"}:
            key = "neutral"
        candidate = (self.default.get(key) or "").strip()
        if candidate:
            return self.default[key]
        neutral = (self.default.get("neutral") or "").strip()
        if neutral:
            return self.default["neutral"]
        for v in self.default.values():
            if v and str(v).strip():
                return str(v)
        return ""


@dataclass(frozen=True)
class BackgroundSlot:
    """Background slot — base scene + lock level + override whitelist."""

    base: str = ""
    lock: BackgroundLockLevel = BackgroundLockLevel.FLEXIBLE
    overrides_allowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityBlock:
    """Quality / identity anchors.

    ``base`` is the common text appended to every non-document prompt
    (equivalent of today's ``PRESERVE_PHOTO_FACE_ONLY + QUALITY_PHOTO +
    LIGHT_INTEGRATION_PHOTO + CAMERA_PHOTO + ANATOMY_PHOTO`` block).

    ``per_model_tail`` is an optional mapping keyed by the A/B model
    name (``"gpt_image_2"`` / ``"nano_banana_2"``) to a short extra
    string appended after ``base``. Empty dict = fall back to whatever
    the model wrapper chooses; a present key overrides the wrapper
    default for that model.
    """

    base: str = ""
    per_model_tail: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StyleSpecV2:
    """Slot-based, version-tagged style specification.

    Registered in the live :class:`src.prompts.style_spec.StyleRegistry`
    via ``register_v2`` (PR1 extension). Lookup key is the same
    ``(mode, key)`` pair as v1 so existing callers keep working.
    """

    key: str
    mode: str  # dating | cv | social

    trigger: str
    background: BackgroundSlot
    clothing: ClothingSlot
    weather: WeatherPolicy
    context_slots: dict[str, tuple[str, ...]]
    quality_identity: QualityBlock

    # Legacy-shaped helpers so the executor / postprocess code that
    # currently reads ``spec.needs_full_body`` / ``spec.output_aspect``
    # / ``spec.generation_mode`` / ``spec.expression`` keeps working
    # without branching on the schema version at every call site.
    expression: str = ""
    needs_full_body: bool = False
    output_aspect: Literal[
        "portrait_4_3",
        "portrait_16_9",
        "square_hd",
        "landscape_4_3",
        "landscape_16_9",
    ] = "portrait_4_3"
    generation_mode: Literal["identity_scene", "scene_preserve"] = "identity_scene"

    # Schema version — always 2 for instances of this class; kept as a
    # field so ``isinstance`` plus ``getattr(spec, "schema_version", 1)``
    # both work for migration-era branching.
    schema_version: int = SCHEMA_VERSION

    # Back-compat shim: some v1 call sites read ``spec.allowed_variations``
    # as a flat per-channel dict. We synthesise one from the slot fields
    # so templates that reach into the spec directly (e.g. the catalog
    # endpoint) do not break when the underlying spec is v2.
    @property
    def allowed_variations(self) -> dict[str, list[str]]:
        return {
            "lighting": list(self.context_slots.get("lighting", ())),
            "angle_placement": list(self.context_slots.get("angle_placement", ())),
            "framing": list(
                self.context_slots.get("framing", ("portrait", "half_body", "full_body"))
            ),
            "weather": list(self.weather.allowed),
            "clothing": list(self.clothing.allowed),
            "background": list(self.background.overrides_allowed),
        }

    # Minimal v1 spec surface so ``_build_mode_prompt`` style helpers do
    # not need a special-case branch before v2 fully ships. These
    # helpers intentionally mirror the method names on v1 specs.
    @property
    def base_scene(self) -> str:
        return self.background.base

    @property
    def scene(self) -> str:
        return self.background.base

    @property
    def clothing_text(self) -> str:
        return self.clothing.text("neutral")

    def clothing_for(self, gender: str = "male") -> str:
        return self.clothing.text(gender)
