"""Composition Safety Layer (CSL) — classifier + policy.

Snapshots the four canonical composition categories defined in the
ТЗ "Composition Safety Layer для генерации изображений людей":

    A. Face Close-Up  — only face / part of the neck
    B. Portrait       — head + shoulders + upper chest
    C. Half Body      — torso + waist region
    D. Full Body      — whole body, readable proportions

Plus an UNKNOWN bucket for fail-closed-safe behaviour when the
upstream face/body detector does not fire.

The policy table is the single source of truth for which framings
and which styles are permissible for each composition class. The
classifier itself is intentionally heuristic-only here (Phase 1);
the optional MediaPipe Pose path lives in
:mod:`src.services.body_landmarks` and only refines this result
when ``settings.body_landmarks_enabled`` is on.

This module is read-only from the prompt pipeline's point of view —
it never touches :mod:`src.prompts.image_gen`,
:mod:`src.prompts.composition_builder`, prompt slots, or quality
anchors. CSL only constrains *inputs* (``framing``, available
styles), and the existing IR builder consumes those constrained
inputs without modification.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CompositionClass(str, Enum):
    """Composition category derived from the uploaded photo."""

    FACE_CLOSEUP = "face_closeup"
    PORTRAIT = "portrait"
    HALF_BODY = "half_body"
    FULL_BODY = "full_body"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: Any) -> "CompositionClass":
        """Best-effort parse: unknown / empty / weird strings → UNKNOWN.

        Cheap helper so callers do not have to wrap ``CompositionClass(x)``
        in their own try/except. The CSL contract treats UNKNOWN as the
        most restrictive bucket (fail-closed-safe), so coercing here is
        safe.
        """
        if isinstance(value, cls):
            return value
        if not value:
            return cls.UNKNOWN
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.UNKNOWN


# Canonical framing values used across the codebase. Kept as a tuple so
# the order doubles as the "preferred fallback" priority (portrait wins
# whenever auto-correcting an invalid framing pick).
_ALL_FRAMINGS: tuple[str, ...] = ("portrait", "half_body", "full_body")


# Policy matrix — see plan / ТЗ. Keys are explicit CompositionClass
# enum members so a typo lands as a KeyError at import time, not a
# silent fall-through during request handling.
_POLICY: dict[CompositionClass, dict[str, Any]] = {
    CompositionClass.FACE_CLOSEUP: {
        "allowed_framings": ("portrait",),
        "forbid_full_body_styles": True,
        "warn_torso_styles": True,
    },
    CompositionClass.PORTRAIT: {
        "allowed_framings": ("portrait", "half_body"),
        "forbid_full_body_styles": True,
        "warn_torso_styles": False,
    },
    CompositionClass.HALF_BODY: {
        "allowed_framings": ("portrait", "half_body", "full_body"),
        "forbid_full_body_styles": False,
        "warn_torso_styles": False,
    },
    CompositionClass.FULL_BODY: {
        "allowed_framings": ("portrait", "half_body", "full_body"),
        "forbid_full_body_styles": False,
        "warn_torso_styles": False,
    },
    # Fail-closed-safe: when the detector fails we treat the photo as
    # the most constrained category so we never accidentally let a
    # head-crop drive a full-body generation.
    CompositionClass.UNKNOWN: {
        "allowed_framings": ("portrait",),
        "forbid_full_body_styles": True,
        "warn_torso_styles": True,
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def allowed_framings(cls: CompositionClass | str) -> list[str]:
    """Return the framings (``portrait`` / ``half_body`` / ``full_body``)
    a UI/bot may surface for this composition class.

    Always returns at least ``["portrait"]`` — every category permits a
    portrait-framed generation (head-and-shoulders is the safest crop
    we can ask any edit model to produce).
    """
    composition = CompositionClass.parse(cls)
    framings = _POLICY[composition]["allowed_framings"]
    return list(framings)


def is_style_forbidden(cls: CompositionClass | str, spec: Any) -> bool:
    """True when the (class, style) pair must be hard-blocked.

    Currently the only forbidden pairing is "full-body style on a class
    that does not allow full-body framing" (FACE_CLOSEUP, PORTRAIT,
    UNKNOWN × ``needs_full_body=True``). The caller must surface this
    in UI via a clear explanation and refuse the generation.
    """
    if spec is None:
        return False
    composition = CompositionClass.parse(cls)
    if not _POLICY[composition]["forbid_full_body_styles"]:
        return False
    return bool(getattr(spec, "needs_full_body", False))


def is_style_risky(cls: CompositionClass | str, spec: Any) -> bool:
    """True when the (class, style) pair should emit a soft warning.

    Currently warns on torso-required styles when the upload is a tight
    head crop (FACE_CLOSEUP / UNKNOWN × ``needs_torso=True``). The
    caller is expected to keep the style selectable but surface a
    "may look unnatural" notice.
    """
    if spec is None:
        return False
    composition = CompositionClass.parse(cls)
    if not _POLICY[composition]["warn_torso_styles"]:
        return False
    return bool(getattr(spec, "needs_torso", False))


def normalise_framing(
    cls: CompositionClass | str,
    framing: str | None,
) -> str:
    """Snap an arbitrary framing pick to the closest allowed value.

    Used by the executor / API as a defense-in-depth normaliser when a
    client sends a framing that the composition policy forbids. We
    intentionally degrade silently to ``portrait`` rather than 400ing
    here — the hard 400 lives in the analyze endpoint with the explicit
    ``FRAMING_NOT_ALLOWED`` code.
    """
    allowed = allowed_framings(cls)
    pick = (framing or "").strip().lower()
    if pick in allowed:
        return pick
    return allowed[0]


def classify_heuristic(
    face_bbox: tuple[int, int, int, int] | None,
    face_area_ratio: float,
    width: int,
    height: int,
    *,
    face_closeup_face_ratio: float = 0.35,
    face_closeup_space_below: float = 1.0,
    portrait_face_ratio: float = 0.18,
    portrait_space_below: float = 2.0,
    half_body_face_ratio: float = 0.06,
    half_body_space_below: float = 4.0,
) -> CompositionClass:
    """Classify composition from FaceDetection signals only.

    Heuristic Phase 1 of CSL — purely a function of the face bounding
    box, the face-area ratio and the frame height. Returns UNKNOWN
    when ``face_bbox`` is missing (detector failure, no face found, etc.)
    so the caller falls into the fail-closed-safe branch.

    Args:
        face_bbox: (x1, y1, x2, y2) in pixel coords or None.
        face_area_ratio: face_bbox area / total image area (0..1).
        width: image width in pixels.
        height: image height in pixels.
        face_closeup_*, portrait_*, half_body_*: tunable thresholds
            (Phase 4 calibration replaces these with values from
            ``settings``).

    Pixel-geometry signals used:
        * ``face_area_ratio`` — bigger face fraction → tighter crop.
        * ``space_below_face`` — pixels between the bottom of the face
          bbox and the bottom of the frame, expressed in face-heights.
          A value < 1.0 means there is no room below the chin for a
          torso, so the upload cannot be anything but a head crop.
    """
    if face_bbox is None or face_area_ratio is None or face_area_ratio <= 0:
        return CompositionClass.UNKNOWN
    if height <= 0 or width <= 0:
        return CompositionClass.UNKNOWN

    try:
        _, _, _, y2 = (int(v) for v in face_bbox)
    except (TypeError, ValueError):
        return CompositionClass.UNKNOWN

    fy1 = int(face_bbox[1])
    face_h = max(1, y2 - fy1)
    space_below = max(0, height - y2) / face_h

    if face_area_ratio >= face_closeup_face_ratio or space_below < face_closeup_space_below:
        return CompositionClass.FACE_CLOSEUP
    if face_area_ratio >= portrait_face_ratio or space_below < portrait_space_below:
        return CompositionClass.PORTRAIT
    if face_area_ratio >= half_body_face_ratio or space_below < half_body_space_below:
        return CompositionClass.HALF_BODY
    return CompositionClass.FULL_BODY


def resolve_effective_framing(
    *,
    user_framing: str | None,
    composition_class: CompositionClass | str,
    spec: Any,
    is_document: bool,
    is_studio_portrait: bool = False,
) -> str:
    """Pick the final framing for a generation using CSL classification.

    v1.65 — single source of truth for "what framing should we actually
    send to the model". Used by both the executor (when a request comes
    in without an explicit framing, or with a framing the policy
    forbids) and the bot (when picking a default for the user). Having
    one resolver keeps the two entrypoints from drifting apart and
    means the bot UI shows the same framing the executor will end up
    generating.

    Priority order:

    1. Document style → always ``portrait``. Document styles
       (passport / visa / 3x4 photos) have a fixed vendor-policy
       framing that does not negotiate.
    2. Studio-portrait style → always ``portrait``. v1.66: explicit
       studio headshot/bust-shot styles (``formal_portrait``,
       ``studio_elegant``) are by-design tight portraits — the
       resolver pins them to ``portrait`` regardless of CSL
       classification or user pick, mirroring the document-style
       behaviour.
    3. ``user_framing`` if the policy permits it for this composition
       class (``user_framing in allowed_framings(composition_class)``).
       Respecting an explicit user pick is the friendliest behaviour.
    4. Style's ``needs_full_body`` if ``full_body`` is in
       ``allowed_framings`` — full-body styles deserve full-body
       framing whenever the upload supports it.
    5. First entry of ``allowed_framings`` in canonical preference
       order (portrait → half_body → full_body). This gives a sane
       default for every composition class.
    6. Fail-closed-safe: ``portrait``. Reached only when the policy
       table is misconfigured; ``portrait`` is the safest output any
       edit model can produce for any reference photo.

    Args:
        user_framing: Framing the user / API caller explicitly asked
            for. ``None`` / empty string means "no explicit pick".
            Invalid values (e.g. ``"square"``) are treated as
            "no explicit pick".
        composition_class: CSL classification of the upload (string or
            enum). Drives ``allowed_framings``.
        spec: StyleSpec for the requested style (v2 or v3). Only
            ``needs_full_body`` is consulted.
        is_document: True when the requested style is a document
            style. Document styles are short-circuited to ``portrait``
            regardless of every other signal.
        is_studio_portrait: True when the requested style is in the
            ``_STUDIO_PORTRAIT_STYLE_KEYS`` whitelist. Studio-portrait
            styles are short-circuited to ``portrait`` (v1.66).

    Returns:
        One of ``"portrait"`` / ``"half_body"`` / ``"full_body"``.
    """
    if is_document or is_studio_portrait:
        return "portrait"

    allowed = allowed_framings(composition_class)
    if not allowed:
        return "portrait"

    pick = (user_framing or "").strip().lower()
    if pick in _ALL_FRAMINGS and pick in allowed:
        return pick

    needs_full_body = bool(getattr(spec, "needs_full_body", False)) if spec is not None else False
    if needs_full_body and "full_body" in allowed:
        return "full_body"

    for canonical in _ALL_FRAMINGS:
        if canonical in allowed:
            return canonical

    return "portrait"


def policy_summary(cls: CompositionClass | str) -> dict[str, Any]:
    """Return a flat dict describing what the policy permits for ``cls``.

    Useful for observability / tests so we can assert on policy without
    parsing tuples by hand.
    """
    composition = CompositionClass.parse(cls)
    entry = _POLICY[composition]
    return {
        "composition_class": composition.value,
        "allowed_framings": list(entry["allowed_framings"]),
        "forbid_full_body_styles": bool(entry["forbid_full_body_styles"]),
        "warn_torso_styles": bool(entry["warn_torso_styles"]),
    }
