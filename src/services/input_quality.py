"""Pre-flight input quality gate.

Analyzes an uploaded photo locally (InsightFace + mediapipe + Laplacian) to decide
whether we should spend a Reve API call on it. The gate is designed to be cheap
(no LLM, no image generation) and to surface precise, actionable reasons to the
user BEFORE any paid API is invoked.

Two levels of findings:
  - blocking issues → HTTP 400, no Reve call, user must re-upload
  - soft warnings   → returned to UI/bot so the user can decide to proceed

See also: src/services/photo_requirements.py for the human-readable texts and
machine codes shared with the web frontend.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from src.config import settings
from src.services.photo_requirements import ISSUE_TEXTS, IssueCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class InputQualityIssue:
    code: str          # machine code, see IssueCode
    severity: str      # "block" | "warn"
    message: str       # short human-readable ru
    suggestion: str    # actionable hint ru

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class InputQualityReport:
    can_generate: bool
    issues: list[InputQualityIssue] = field(default_factory=list)

    # Metrics (for prompt conditioning downstream)
    face_area_ratio: float = 0.0
    face_center_offset: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    blur_face: float = -1.0
    blur_full: float = -1.0
    hair_bg_contrast: float = -1.0
    num_faces: int = 0
    width: int = 0
    height: int = 0

    @property
    def blocking(self) -> list[InputQualityIssue]:
        return [i for i in self.issues if i.severity == "block"]

    @property
    def soft_warnings(self) -> list[InputQualityIssue]:
        return [i for i in self.issues if i.severity == "warn"]

    @property
    def first_block_message(self) -> str:
        b = self.blocking
        return b[0].message if b else ""

    def to_public_dict(self) -> dict[str, Any]:
        """Dict shape safe to expose to the frontend (no raw metrics)."""
        return {
            "can_generate": self.can_generate,
            "soft_warnings": [i.to_dict() for i in self.soft_warnings],
            "blocking_issues": [i.to_dict() for i in self.blocking],
        }

    def to_prompt_hints(self) -> dict[str, Any]:
        """Compact metrics dict used by prompt builder for conditional injections."""
        return {
            "face_area_ratio": self.face_area_ratio,
            "face_center_offset": self.face_center_offset,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "hair_bg_contrast": self.hair_bg_contrast,
            "blur_face": self.blur_face,
        }


# ---------------------------------------------------------------------------
# Issue builder helper
# ---------------------------------------------------------------------------


def _issue(code: str, severity: str) -> InputQualityIssue:
    spec = ISSUE_TEXTS.get(code, {"message": code, "suggestion": ""})
    return InputQualityIssue(
        code=code,
        severity=severity,
        message=spec["message"],
        suggestion=spec["suggestion"],
    )


# ---------------------------------------------------------------------------
# Low-level measurements
# ---------------------------------------------------------------------------


def _laplacian_variance(arr: np.ndarray) -> float:
    """Variance of Laplacian on a 2D grayscale array. Higher = sharper."""
    if arr.ndim != 2 or arr.shape[0] < 3 or arr.shape[1] < 3:
        return -1.0
    a = arr.astype(np.float64)
    lap = (
        -a[:-2, 1:-1] - a[2:, 1:-1]
        - a[1:-1, :-2] - a[1:-1, 2:]
        + 4 * a[1:-1, 1:-1]
    )
    return float(np.var(lap))


def _detect_faces(arr_rgb: np.ndarray) -> list[Any]:
    """Return InsightFace detections (empty list on any failure)."""
    try:
        from src.services.identity import _get_app
        return list(_get_app().get(arr_rgb))
    except Exception:
        logger.debug("InsightFace detection failed", exc_info=True)
        return []


def _hair_bg_contrast(arr_rgb: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    """Rough contrast between the area just above/around the head and the head itself.

    We measure mean L-channel (luminance) difference between a band around the
    top-half of the head bbox and the surrounding ring. Low value → background
    is similar to hair → replacement likely to bleed.

    Returns a normalized value in 0..1 (diff / 255).
    """
    h, w = arr_rgb.shape[:2]
    x1, y1, x2, y2 = bbox
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)

    # Inner region: upper 60% of the face bbox (where hair usually is)
    ix1, ix2 = max(0, x1), min(w, x2)
    iy1 = max(0, y1 - int(bh * 0.20))
    iy2 = max(iy1 + 1, y1 + int(bh * 0.40))
    inner = arr_rgb[iy1:iy2, ix1:ix2]

    # Outer ring: padded band around the head
    pad_x = int(bw * 0.40)
    pad_y = int(bh * 0.40)
    ox1, oy1 = max(0, x1 - pad_x), max(0, iy1 - pad_y)
    ox2, oy2 = min(w, x2 + pad_x), min(h, iy2 + pad_y)
    outer = arr_rgb[oy1:oy2, ox1:ox2]

    if inner.size == 0 or outer.size == 0:
        return -1.0

    def _lum(block: np.ndarray) -> float:
        b = block.astype(np.float32)
        return float(0.299 * b[..., 0].mean() + 0.587 * b[..., 1].mean() + 0.114 * b[..., 2].mean())

    inner_l = _lum(inner)
    outer_l = _lum(outer)
    return abs(inner_l - outer_l) / 255.0


def _pose_angles(face: Any) -> tuple[float, float, float]:
    """Extract (yaw, pitch, roll) in degrees from an InsightFace detection.

    InsightFace exposes pose as [pitch, yaw, roll] in some builds, [yaw, pitch, roll]
    in others. We query `pose` attribute and fall back to zeros on any mismatch.
    """
    pose = getattr(face, "pose", None)
    if pose is None:
        return 0.0, 0.0, 0.0
    try:
        arr = np.asarray(pose, dtype=np.float32).flatten()
        if arr.size < 3:
            return 0.0, 0.0, 0.0
        # buffalo_l returns [pitch, yaw, roll] (degrees)
        pitch, yaw, roll = float(arr[0]), float(arr[1]), float(arr[2])
        return yaw, pitch, roll
    except Exception:
        return 0.0, 0.0, 0.0


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------


def analyze_input_quality(image_bytes: bytes) -> InputQualityReport:
    """Run all pre-flight checks and return a report.

    This function never raises on invalid input; it returns a report where
    `can_generate=False` plus a blocking issue explaining the problem.
    """
    report = InputQualityReport(can_generate=True)

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.INVALID_IMAGE, "block"))
        return report

    w, h = img.size
    report.width, report.height = w, h

    min_res = int(getattr(settings, "input_min_resolution", 400))
    if w < min_res or h < min_res:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.LOW_RESOLUTION, "block"))

    arr_rgb = np.array(img)
    gray = np.array(img.convert("L"))
    blur_full = _laplacian_variance(gray)
    report.blur_full = blur_full
    min_blur_full = float(getattr(settings, "input_min_blur_full", 60.0))
    if 0 <= blur_full < min_blur_full:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.BLURRY_PHOTO, "block"))

    faces = _detect_faces(arr_rgb)
    report.num_faces = len(faces)
    if not faces:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.NO_FACE, "block"))
        return report

    faces_sorted = sorted(faces, key=lambda f: float(f.det_score), reverse=True)
    primary = faces_sorted[0]

    try:
        x1, y1, x2, y2 = [int(v) for v in primary.bbox]
    except Exception:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.NO_FACE, "block"))
        return report

    fw = max(1, x2 - x1)
    fh = max(1, y2 - y1)
    face_area = fw * fh
    total_area = max(1, w * h)
    face_area_ratio = face_area / total_area
    report.face_area_ratio = round(face_area_ratio, 4)

    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    report.face_center_offset = round(
        max(abs(cx / w - 0.5), abs(cy / h - 0.5)) * 2.0, 3,
    )

    yaw, pitch, roll = _pose_angles(primary)
    report.yaw, report.pitch, report.roll = round(yaw, 1), round(pitch, 1), round(roll, 1)

    face_crop_gray = gray[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    blur_face = _laplacian_variance(face_crop_gray)
    report.blur_face = blur_face

    report.hair_bg_contrast = round(
        _hair_bg_contrast(arr_rgb, (x1, y1, x2, y2)), 3,
    )

    min_face_ratio = float(getattr(settings, "input_min_face_area_ratio", 0.04))
    warn_face_ratio = float(getattr(settings, "input_warn_face_area_ratio", 0.10))
    min_blur_face = float(getattr(settings, "input_min_blur_face", 40.0))

    if face_area_ratio < min_face_ratio:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.FACE_TOO_SMALL, "block"))

    if 0 <= blur_face < min_blur_face:
        report.can_generate = False
        report.issues.append(_issue(IssueCode.FACE_BLURRED, "block"))

    if len(faces) > 1:
        secondary = faces_sorted[1]
        try:
            s_x1, s_y1, s_x2, s_y2 = [int(v) for v in secondary.bbox]
            sec_area = max(1, s_x2 - s_x1) * max(1, s_y2 - s_y1)
            if sec_area / total_area >= 0.10:
                report.can_generate = False
                report.issues.append(_issue(IssueCode.MULTIPLE_FACES, "block"))
        except Exception:
            pass

    # Soft warnings (only emitted if not already blocked on the same axis)
    blocked_codes = {i.code for i in report.blocking}

    if (
        IssueCode.FACE_TOO_SMALL not in blocked_codes
        and face_area_ratio < warn_face_ratio
    ):
        report.issues.append(_issue(IssueCode.FACE_SMALL_WARN, "warn"))

    if report.face_center_offset > 0.35:
        report.issues.append(_issue(IssueCode.FACE_OFF_CENTER, "warn"))

    if abs(yaw) > 30.0 or abs(pitch) > 25.0:
        report.issues.append(_issue(IssueCode.NOT_FRONTAL, "warn"))

    if 0 <= report.hair_bg_contrast < 0.08:
        report.issues.append(_issue(IssueCode.HAIR_BG_SIMILAR, "warn"))

    logger.info(
        "InputQuality: face_area=%.3f center_off=%.2f yaw=%.1f blur_f=%.0f blur_full=%.0f "
        "hair_bg=%.2f n_faces=%d can_gen=%s blocks=%s warns=%s",
        report.face_area_ratio, report.face_center_offset, report.yaw,
        report.blur_face, report.blur_full, report.hair_bg_contrast,
        report.num_faces, report.can_generate,
        [i.code for i in report.blocking],
        [i.code for i in report.soft_warnings],
    )

    return report
