"""Tests for :mod:`src.services.body_landmarks` (CSL Phase 2).

Covers the three concerns of the Pose path:

1. **Soft failure** — a missing/broken MediaPipe wheel must yield
   ``None`` (the caller falls back to the heuristic) without raising.
2. **Landmark → CompositionClass mapping** — the policy decoder is a
   pure function and we exercise the full visibility lattice.
3. **Detector caching** — once MediaPipe failed to load we never retry
   the import; once it succeeded we reuse the cached instance.

The full ground-truth comparison (Pose vs heuristic vs hand-labels) is
the responsibility of ``scripts/calibrate_composition_thresholds.py``
in Phase 4.2 — these tests verify the contract of the detector module
itself.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np

from src.services import body_landmarks as bl
from src.services.composition_safety import CompositionClass


# ---------------------------------------------------------------------------
# classify_from_landmarks — policy lattice
# ---------------------------------------------------------------------------


def test_classify_full_body_when_knees_visible():
    cls = bl.classify_from_landmarks(
        bl.BodyLandmarks(shoulders_visible=True, hips_visible=True, knees_visible=True)
    )
    assert cls is CompositionClass.FULL_BODY


def test_classify_half_body_when_hips_visible_no_knees():
    cls = bl.classify_from_landmarks(
        bl.BodyLandmarks(shoulders_visible=True, hips_visible=True, knees_visible=False)
    )
    assert cls is CompositionClass.HALF_BODY


def test_classify_portrait_when_shoulders_visible_no_hips():
    cls = bl.classify_from_landmarks(
        bl.BodyLandmarks(shoulders_visible=True, hips_visible=False, knees_visible=False)
    )
    assert cls is CompositionClass.PORTRAIT


def test_classify_face_closeup_when_only_face_visible():
    cls = bl.classify_from_landmarks(
        bl.BodyLandmarks(shoulders_visible=False, hips_visible=False, knees_visible=False)
    )
    assert cls is CompositionClass.FACE_CLOSEUP


def test_classify_treats_knees_alone_as_full_body():
    """Defensive: if Pose somehow returns ``knees=True`` without
    ``hips=True`` we still classify as FULL_BODY — the contract is
    "knees imply hips" but the policy table never reads ``hips`` once
    knees are visible."""
    cls = bl.classify_from_landmarks(
        bl.BodyLandmarks(shoulders_visible=False, hips_visible=False, knees_visible=True)
    )
    assert cls is CompositionClass.FULL_BODY


# ---------------------------------------------------------------------------
# detect_landmarks — fail-soft behaviour
# ---------------------------------------------------------------------------


def test_detect_landmarks_returns_none_when_mediapipe_missing(monkeypatch):
    """When MediaPipe can't be imported (slim container, GLIBC issue,
    pip omission), ``detect_landmarks`` must return ``None`` so the
    caller falls back to the heuristic — never raise."""
    bl.reset_detector_cache()
    monkeypatch.setitem(sys.modules, "mediapipe", None)

    image = np.zeros((640, 480, 3), dtype=np.uint8)
    result = bl.detect_landmarks(image)
    assert result is None
    # Subsequent calls short-circuit through the poisoned cache.
    assert bl._pose_available is False
    bl.reset_detector_cache()


def test_detect_landmarks_returns_none_when_process_raises(monkeypatch):
    """A native crash inside ``Pose.process()`` must NOT propagate —
    the user shouldn't lose their generation because MediaPipe segfaulted."""
    bl.reset_detector_cache()

    boom = MagicMock()
    boom.process = MagicMock(side_effect=RuntimeError("native crash"))
    monkeypatch.setattr(bl, "_pose_detector", boom)
    monkeypatch.setattr(bl, "_pose_available", True)

    image = np.zeros((640, 480, 3), dtype=np.uint8)
    assert bl.detect_landmarks(image) is None
    bl.reset_detector_cache()


def test_detect_landmarks_returns_none_when_no_pose_found(monkeypatch):
    """No human in frame → ``pose_landmarks=None`` → caller keeps the
    heuristic verdict."""
    bl.reset_detector_cache()
    detector = MagicMock()
    detector.process = MagicMock(return_value=MagicMock(pose_landmarks=None))
    monkeypatch.setattr(bl, "_pose_detector", detector)
    monkeypatch.setattr(bl, "_pose_available", True)

    image = np.zeros((640, 480, 3), dtype=np.uint8)
    assert bl.detect_landmarks(image) is None
    bl.reset_detector_cache()


def test_detect_landmarks_reads_visibility_threshold(monkeypatch):
    """The ``VISIBILITY_THRESHOLD`` constant must gate the boolean
    flags — anything strictly under the threshold counts as "not in
    frame"."""
    bl.reset_detector_cache()

    # Build a synthetic ``pose_landmarks.landmark`` sequence: shoulders
    # at visibility=0.9 (visible), hips at 0.4 (not visible), knees at
    # 0.6 (visible).
    landmark_list = [MagicMock(visibility=0.0) for _ in range(33)]
    landmark_list[11].visibility = 0.9  # left shoulder
    landmark_list[12].visibility = 0.9  # right shoulder
    landmark_list[23].visibility = 0.4  # left hip
    landmark_list[24].visibility = 0.4  # right hip
    landmark_list[25].visibility = 0.6  # left knee
    landmark_list[26].visibility = 0.6  # right knee

    result_obj = MagicMock()
    result_obj.pose_landmarks.landmark = landmark_list

    detector = MagicMock()
    detector.process = MagicMock(return_value=result_obj)
    monkeypatch.setattr(bl, "_pose_detector", detector)
    monkeypatch.setattr(bl, "_pose_available", True)

    image = np.zeros((640, 480, 3), dtype=np.uint8)
    out = bl.detect_landmarks(image)
    assert out is not None
    assert out.shoulders_visible is True
    assert out.hips_visible is False  # 0.4 < 0.5 threshold
    assert out.knees_visible is True
    bl.reset_detector_cache()


# ---------------------------------------------------------------------------
# _get_pose_detector — caching contract
# ---------------------------------------------------------------------------


def test_pose_import_failure_is_cached(monkeypatch):
    """After a failed import, subsequent calls must NOT retry the
    expensive ``import mediapipe`` — we cache the negative result."""
    bl.reset_detector_cache()

    # Force the first ``import mediapipe`` to raise.
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    assert bl._get_pose_detector() is None
    assert bl._pose_available is False

    # Replace the module with one that *would* succeed — the cached
    # negative result means we still get None.
    fake_module = types.ModuleType("mediapipe")
    fake_module.solutions = types.SimpleNamespace(
        pose=types.SimpleNamespace(Pose=MagicMock(return_value=MagicMock()))
    )
    monkeypatch.setitem(sys.modules, "mediapipe", fake_module)
    assert bl._get_pose_detector() is None  # still cached as failed
    bl.reset_detector_cache()


def test_pose_detector_is_reused_after_success(monkeypatch):
    """A successful detector instance is reused across calls."""
    bl.reset_detector_cache()

    instance = MagicMock(name="pose_instance")
    fake_module = types.ModuleType("mediapipe")
    fake_module.solutions = types.SimpleNamespace(
        pose=types.SimpleNamespace(Pose=MagicMock(return_value=instance))
    )
    monkeypatch.setitem(sys.modules, "mediapipe", fake_module)

    first = bl._get_pose_detector()
    second = bl._get_pose_detector()
    assert first is instance
    assert second is instance
    # And the constructor was only called once — caching is by-reference.
    assert fake_module.solutions.pose.Pose.call_count == 1
    bl.reset_detector_cache()
