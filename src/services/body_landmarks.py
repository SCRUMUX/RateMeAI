"""MediaPipe Pose-based body landmark detector for CSL Phase 2.

This module is the optional "Pose refinement" path of the Composition
Safety Layer (CSL). When ``settings.body_landmarks_enabled`` is on,
:mod:`src.services.input_quality` calls into this module after the
heuristic classifier has produced its answer. The Pose detector emits
shoulder / hip / knee visibility flags which the classifier promotes
to a more precise composition class.

Failure mode: any error inside this module — missing MediaPipe wheel,
GLIBC mismatch on slim containers, native segfault inside the
solution graph — degrades to ``return None``. The caller treats that
as "Pose path declined to answer" and keeps the heuristic result.
We never raise to the upstream input_quality flow.

Lifecycle:
    * The detector instance is created lazily on first call so import
      cost stays at zero when the feature flag is off.
    * Once created, the instance is reused across calls. MediaPipe's
      ``Pose`` object is thread-safe for ``process()`` but we run it
      inside ``asyncio.to_thread`` from pre_analyze, so concurrency is
      naturally bounded.
    * On any failure during construction we flip ``_pose_available``
      to ``False`` and never retry the import — re-importing
      ``mediapipe`` on every request would be expensive.

This file deliberately does NOT depend on
:mod:`src.services.composition_safety` at import time to keep the two
modules orthogonal — the policy table can be reloaded without
touching the detector cache, and vice versa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# Cached detector instance + availability flag. ``None`` means "not yet
# tried"; ``False`` means "already tried, failed" (so we skip retries);
# any other value is a live MediaPipe Pose detector instance.
_pose_detector: Any | None = None
_pose_available: bool | None = None

# A landmark with ``visibility`` below this threshold is considered
# "not in frame". MediaPipe's docs treat 0.5 as the canonical cutoff;
# higher values reduce false positives at the cost of accepting tighter
# crops as "shoulders visible". We track this with a constant rather
# than a setting because tweaking it changes the policy semantics and
# should go through a code review, not an env-var.
VISIBILITY_THRESHOLD: float = 0.5

# MediaPipe Pose landmark indices we care about. See
# https://google.github.io/mediapipe/solutions/pose.html#pose-landmark-model-blazepose-ghum-3d
# for the full landmark map.
_IDX_LEFT_SHOULDER = 11
_IDX_RIGHT_SHOULDER = 12
_IDX_LEFT_HIP = 23
_IDX_RIGHT_HIP = 24
_IDX_LEFT_KNEE = 25
_IDX_RIGHT_KNEE = 26


@dataclass(frozen=True)
class BodyLandmarks:
    """Visibility flags for the body parts CSL cares about.

    Boolean rather than the raw probability so the classifier stays
    trivial — Pose's visibility is already a calibrated probability
    inside [0, 1] and the policy is a step function around 0.5.
    """

    shoulders_visible: bool
    hips_visible: bool
    knees_visible: bool


def _get_pose_detector():
    """Return a lazily-constructed MediaPipe Pose detector or ``None``.

    The detector is created with the fastest model tier (complexity=0)
    and segmentation disabled — we only need landmark coordinates and
    visibilities, so the heavier tiers would be a waste. Errors here
    poison ``_pose_available`` so subsequent calls short-circuit
    immediately instead of paying the cost of a failing import.
    """
    global _pose_detector, _pose_available

    if _pose_available is False:
        return None
    if _pose_detector is not None:
        return _pose_detector

    try:
        import mediapipe as mp

        _pose_detector = mp.solutions.pose.Pose(
            static_image_mode=True,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=0.5,
        )
        _pose_available = True
        logger.info("CSL: MediaPipe Pose detector loaded")
        return _pose_detector
    except Exception as exc:
        _pose_available = False
        _pose_detector = None
        logger.info(
            "CSL: MediaPipe Pose unavailable (%s) — falling back to heuristic",
            exc,
        )
        return None


def detect_landmarks(image_rgb: np.ndarray) -> BodyLandmarks | None:
    """Run MediaPipe Pose on an RGB image and return visibility flags.

    Args:
        image_rgb: H×W×3 uint8 array in RGB order. The detector copes
            with arbitrary aspect ratios — we do not crop or resize
            because the heuristic classifier operates on the same
            buffer and we want both signals to see the exact same
            frame.

    Returns:
        ``BodyLandmarks`` on success, ``None`` if:
          * MediaPipe couldn't be loaded (missing wheel, native deps);
          * Pose returned no landmarks (no human detected in frame);
          * ``process()`` raised at the native layer.

        The caller (``analyze_input_quality``) treats ``None`` as
        "Pose declined" and keeps the heuristic answer — never an
        error.
    """
    detector = _get_pose_detector()
    if detector is None:
        return None

    try:
        result = detector.process(image_rgb)
    except Exception:
        logger.debug("CSL: Pose process() raised", exc_info=True)
        return None

    if not getattr(result, "pose_landmarks", None):
        return None

    try:
        lm = result.pose_landmarks.landmark
    except Exception:
        logger.debug("CSL: Pose result has no .landmark sequence", exc_info=True)
        return None

    def _vis(idx: int) -> bool:
        try:
            return float(lm[idx].visibility) >= VISIBILITY_THRESHOLD
        except (IndexError, AttributeError, TypeError, ValueError):
            return False

    return BodyLandmarks(
        shoulders_visible=_vis(_IDX_LEFT_SHOULDER) and _vis(_IDX_RIGHT_SHOULDER),
        hips_visible=_vis(_IDX_LEFT_HIP) and _vis(_IDX_RIGHT_HIP),
        knees_visible=_vis(_IDX_LEFT_KNEE) and _vis(_IDX_RIGHT_KNEE),
    )


def classify_from_landmarks(lm: BodyLandmarks):
    """Promote landmark visibilities into a CompositionClass.

    Decision order matches the visibility hierarchy: knees imply hips
    imply shoulders, so the most-specific (most permissive for
    framing) class wins. If even shoulders aren't visible we mark
    the upload as FACE_CLOSEUP — the Pose detector found a human but
    nothing below the neck.

    Imported lazily so this module stays importable in test
    environments where ``src.services.composition_safety`` may be
    monkey-patched but ``body_landmarks`` is not.
    """
    from src.services.composition_safety import CompositionClass

    if lm.knees_visible:
        return CompositionClass.FULL_BODY
    if lm.hips_visible:
        return CompositionClass.HALF_BODY
    if lm.shoulders_visible:
        return CompositionClass.PORTRAIT
    return CompositionClass.FACE_CLOSEUP


def reset_detector_cache() -> None:
    """Test-only helper: clear the cached detector instance.

    Lets unit tests inject a mock for ``mediapipe`` and re-trigger the
    lazy import. Production callers never need this.
    """
    global _pose_detector, _pose_available
    _pose_detector = None
    _pose_available = None
