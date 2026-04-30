"""Style schema v3 — universal slot composition with random sampling.

Stage 1 of the prompt-pipeline-overhaul (2026-04). Strictly additive
on top of :mod:`src.prompts.style_schema_v2`: a JSON entry opts into v3
by setting ``"schema_version": 3``, otherwise the v2 / v1 loaders
keep handling it.

Why a v3 schema?
================

The v2 schema mixes scene, lighting, materials and time-of-day into a
single ``background.base`` string (e.g. ``"clean modern minimalist
room, indirect lighting, neutral walls, warm ambient glow"``). That
hurts in three ways:

* The headline motif of the style — "mirror" for ``mirror_aesthetic``,
  "Burj Khalifa" for the Dubai style — is buried in the same string
  as decorative fluff and sometimes missing entirely (Category D in
  ``scripts/migrations/2026_04_prompt_quality/audit_report.md``).
* User overrides for individual slots conflict with the rigid wording
  in ``base`` ("warm ambient glow" + user's "cool blue" produces a
  schizophrenic prompt).
* Without explicit pools per channel the random sampler has nothing
  to roll, so first-time generations of the same style by ten
  different users look identical.

The v3 schema fixes this by exposing every mutable axis as its own
pool:

* :attr:`StyleSpecV3.trigger_pool` — non-empty list of equivalent
  motif phrasings. The slot sampler picks one per generation; the
  user CANNOT erase it (this is the inviolable axis that anchors the
  style — Burj Khalifa stays Burj Khalifa no matter which knobs the
  user twists).
* :attr:`StyleSpecV3.scene_anchor` — a single dry sentence describing
  the scene WITHOUT lighting / weather / time-of-day adjectives.
* :attr:`StyleSpecV3.scene_overrides` — alternative scene anchors the
  user (or the variation engine) may pick instead.
* :attr:`StyleSpecV3.ambient` — per-channel pools for lighting,
  weather, time_of_day, season, materials and framing hints.
* :attr:`StyleSpecV3.clothing` — reused unchanged from v2.
* :attr:`StyleSpecV3.quality_identity` — reused unchanged from v2.

The slot sampler (:mod:`src.prompts.slot_sampler`) consumes a
``StyleSpecV3`` plus user ``input_hints`` plus an optional ``seed``
and returns a :class:`ResolvedSlots` with concrete picks. The
composition builder converts that into a :class:`CompositionIR`,
which the per-model wrappers stringify exactly as on the v2 path —
so downstream code (model adapters, post-processing, executor) stays
untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    ClothingSlot,
    QualityBlock,
)


SCHEMA_VERSION_V3 = 3


@dataclass(frozen=True)
class AmbientPools:
    """Per-channel whitelists used by the slot sampler.

    Each field holds the values the sampler may roll for that channel
    when the user has not pinned a specific value. Empty tuple = the
    channel is closed for this style (sampler outputs ``""`` and the
    composition builder drops the channel from the prompt).

    ``materials`` and ``framing_hint`` are reserved for Stage 2 +
    Stage 3 — currently unused by the core sampler. They are accepted
    here so the migration script can populate them now without a
    second loader change.
    """

    lighting: tuple[str, ...] = ()
    weather: tuple[str, ...] = ()
    time_of_day: tuple[str, ...] = ()
    season: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    framing_hint: tuple[str, ...] = ()

    def for_channel(self, channel: str) -> tuple[str, ...]:
        return getattr(self, channel, ())


@dataclass(frozen=True)
class StyleSpecV3:
    """Slot-based, version-tagged style specification with random pools.

    The runtime contract:

    * ``trigger_pool`` MUST contain at least one entry. The slot
      sampler enforces this; the loader rejects entries that fail.
    * ``scene_anchor`` SHOULD avoid embedding lighting / weather /
      time-of-day descriptors — those belong in :attr:`ambient`. The
      Stage 2 audit fails the build when ``scene_anchor`` contains
      forbidden tokens like "lighting", "rainy", "golden hour".
    * ``ambient`` channels are independent: the sampler rolls each
      separately, so picking "winter" for ``season`` does not couple
      to ``lighting``.
    * ``clothing.allowed`` and ``scene_overrides`` provide the user-
      facing override pools surfaced by :class:`StyleSettingsModal`.
      An empty pool means "closed channel" for the modal but the
      sampler may still output the default if the user asked for one.
    """

    key: str
    mode: str  # dating | cv | social

    trigger_pool: tuple[str, ...]
    scene_anchor: str

    clothing: ClothingSlot
    quality_identity: QualityBlock

    scene_overrides: tuple[str, ...] = ()
    background_lock: BackgroundLockLevel = BackgroundLockLevel.SEMI
    ambient: AmbientPools = field(default_factory=AmbientPools)

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

    schema_version: int = SCHEMA_VERSION_V3

    def __post_init__(self) -> None:  # noqa: D401 — dataclass hook
        if not self.trigger_pool:
            raise ValueError(
                f"StyleSpecV3 {self.key!r}: trigger_pool must contain at "
                "least one entry. The trigger is the inviolable motif "
                "of the style and cannot be empty."
            )

    # ------------------------------------------------------------------
    # v2-compatibility helpers. The runtime registry stores v3 entries
    # in their own ``_v3_by_key`` map; consumers that still expect a
    # v2 shape (catalog endpoint, modal payload) read these properties.
    # ------------------------------------------------------------------

    @property
    def base_scene(self) -> str:
        """Scene anchor exposed as legacy ``base_scene`` for catalogs."""
        return self.scene_anchor

    @property
    def scene(self) -> str:
        return self.scene_anchor

    @property
    def trigger(self) -> str:
        """First trigger of the pool — for code paths that pre-date v3
        and still read a single ``trigger`` string. The slot sampler
        always re-rolls anyway."""
        return self.trigger_pool[0] if self.trigger_pool else ""

    @property
    def clothing_text(self) -> str:
        return self.clothing.text("neutral")

    def clothing_for(self, gender: str = "male") -> str:
        return self.clothing.text(gender)

    @property
    def allowed_variations(self) -> dict[str, list[str]]:
        """Modal payload — same shape as the v2 helper.

        ``framing`` is included even when its pool is empty so the
        legacy modal keeps showing the three default chips
        (portrait / half_body / full_body). ``trigger_pool`` is
        deliberately excluded here: triggers are controlled via a
        separate ``trigger_choice`` field in the modal because they
        are never erasable.
        """
        return {
            "lighting": list(self.ambient.lighting),
            "weather": list(self.ambient.weather),
            "time_of_day": list(self.ambient.time_of_day),
            "season": list(self.ambient.season),
            "background": list(self.scene_overrides),
            "clothing": list(self.clothing.allowed),
            "framing": list(
                self.ambient.framing_hint or ("portrait", "half_body", "full_body")
            ),
        }


@dataclass(frozen=True)
class ResolvedSlots:
    """Concrete per-channel picks produced by the slot sampler.

    The ``random_picks`` and ``user_overrides`` partitions let the
    executor persist exactly what was rolled (for replay / "Другой
    вариант" anti-repeat) and what the user explicitly fixed (for
    badge rendering in the UI). ``substitutions`` mirrors the v2 IR
    field — invalid user values that got softly substituted from the
    whitelist appear here so the executor can surface a notice.
    """

    trigger: str
    scene: str
    lighting: str = ""
    weather: str = ""
    time_of_day: str = ""
    season: str = ""
    clothing: str = ""
    expression: str = ""
    random_picks: dict[str, str] = field(default_factory=dict)
    user_overrides: dict[str, str] = field(default_factory=dict)
    substitutions: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Flat serialisable dict — used for DB persistence + API
        response so the frontend can render badges of what was chosen."""
        return {
            "trigger": self.trigger,
            "scene": self.scene,
            "lighting": self.lighting,
            "weather": self.weather,
            "time_of_day": self.time_of_day,
            "season": self.season,
            "clothing": self.clothing,
            "random_picks": dict(self.random_picks),
            "user_overrides": dict(self.user_overrides),
            "substitutions": [dict(s) for s in self.substitutions],
        }
