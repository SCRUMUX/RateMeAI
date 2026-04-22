"""Pre-flight input quality gate.

Analyzes an uploaded photo locally (MediaPipe FaceDetection + Laplacian)
to decide whether we should spend a Reve API call on it. The gate is
designed to be cheap (no LLM, no image generation) and to surface
precise, actionable reasons to the user BEFORE any paid API is invoked.

Privacy note: we use only MediaPipe FaceDetection here, which returns a
bounding box plus a handful of keypoints (eyes, nose, ears, mouth). No
face-recognition feature vector (embedding) is computed or stored.

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


_mp_detector = None
_mp_available: bool | None = None


def _get_mp_detector():
    """Lazy-load MediaPipe FaceDetection (full-range model)."""
    global _mp_detector, _mp_available
    if _mp_available is False:
        return None
    if _mp_detector is not None:
        return _mp_detector
    try:
        import mediapipe as mp
        _mp_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.4,
        )
        _mp_available = True
        return _mp_detector
    except Exception:
        _mp_available = False
        logger.info("MediaPipe FaceDetection unavailable — input-quality face gate degraded")
        return None


@dataclass
class _MPFace:
    """Normalized face detection with the fields input-quality needs.

    Mirrors the subset of the InsightFace `Face` shape previously relied on:
    ``bbox`` (x1,y1,x2,y2), ``det_score``, and a ``pose`` array we derive
    from MediaPipe keypoints (MediaPipe does not expose head pose natively).
    """
    bbox: tuple[int, int, int, int]
    det_score: float
    keypoints: dict[str, tuple[float, float]]

    @property
    def pose(self) -> tuple[float, float, float]:
        """Approximate (yaw, pitch, roll) in degrees from 2D keypoints.

        Heuristic, not calibrated — the caller only uses a >30° yaw / >25°
        pitch heuristic to emit soft warnings, so rough accuracy is fine.
        """
        kp = self.keypoints
        left_eye = kp.get("left_eye")
        right_eye = kp.get("right_eye")
        nose = kp.get("nose_tip")
        if not (left_eye and right_eye and nose):
            return 0.0, 0.0, 0.0

        import math

        eye_mid_x = (left_eye[0] + right_eye[0]) / 2.0
        eye_mid_y = (left_eye[1] + right_eye[1]) / 2.0
        eye_dist = math.hypot(right_eye[0] - left_eye[0], right_eye[1] - left_eye[1])
        if eye_dist <= 1e-6:
            return 0.0, 0.0, 0.0

        # Yaw: horizontal offset of nose from midpoint between eyes (in eye-width units)
        yaw_norm = (nose[0] - eye_mid_x) / eye_dist
        yaw = max(-60.0, min(60.0, yaw_norm * 60.0))

        # Pitch: vertical offset of nose below eye-line (expected ~0.5×eye_dist for frontal)
        pitch_norm = (nose[1] - eye_mid_y) / eye_dist - 0.5
        pitch = max(-60.0, min(60.0, pitch_norm * 60.0))

        # Roll: angle of the eye line
        roll_rad = math.atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0])
        roll = math.degrees(roll_rad)

        return float(yaw), float(pitch), float(roll)


def _detect_faces(arr_rgb: np.ndarray) -> list[_MPFace]:
    """Return MediaPipe face detections normalized to the local _MPFace struct."""
    detector = _get_mp_detector()
    if detector is None:
        return []
    try:
        result = detector.process(arr_rgb)
    except Exception:
        logger.debug("MediaPipe face detection failed", exc_info=True)
        return []
    if not result.detections:
        return []

    h, w = arr_rgb.shape[:2]
    out: list[_MPFace] = []
    for det in result.detections:
        try:
            box = det.location_data.relative_bounding_box
            x1 = max(0, int(box.xmin * w))
            y1 = max(0, int(box.ymin * h))
            x2 = min(w, int((box.xmin + box.width) * w))
            y2 = min(h, int((box.ymin + box.height) * h))
            if x2 <= x1 or y2 <= y1:
                continue

            # MediaPipe keypoint order (face_detection): 0=RIGHT_EYE, 1=LEFT_EYE,
            # 2=NOSE_TIP, 3=MOUTH_CENTER, 4=RIGHT_EAR_TRAGION, 5=LEFT_EAR_TRAGION.
            kps_raw = list(det.location_data.relative_keypoints)
            names = ("right_eye", "left_eye", "nose_tip", "mouth_center",
                     "right_ear", "left_ear")
            keypoints: dict[str, tuple[float, float]] = {}
            for name, kp in zip(names, kps_raw):
                keypoints[name] = (kp.x * w, kp.y * h)

            score = float(det.score[0]) if det.score else 0.0
            out.append(_MPFace(
                bbox=(x1, y1, x2, y2),
                det_score=score,
                keypoints=keypoints,
            ))
        except Exception:
            continue
    return out


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
    """Return (yaw, pitch, roll) for a detection; works with _MPFace via its ``pose``.

    Kept as a function for backward compatibility with tests that call it
    directly. Any object exposing a ``.pose`` attribute with three values
    is accepted.
    """
    pose = getattr(face, "pose", None)
    if pose is None:
        return 0.0, 0.0, 0.0
    try:
        arr = np.asarray(pose, dtype=np.float32).flatten()
        if arr.size < 3:
            return 0.0, 0.0, 0.0
        return float(arr[0]), float(arr[1]), float(arr[2])
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
        # Fail-soft when MediaPipe itself is unavailable in this container
        # (common on slim images missing libGL/libEGL). We must not block
        # every user with NO_FACE just because the detector failed to load —
        # identity preservation is re-checked by the VLM gate after
        # generation (see src/services/quality_gates.py). Soft-warn the
        # user instead so they understand the preview is not face-verified.
        if _mp_available is False:
            report.issues.append(_issue(IssueCode.FACE_DETECTOR_UNAVAILABLE, "warn"))
            logger.warning(
                "input_quality: MediaPipe unavailable — skipping hard NO_FACE block"
            )
            return report
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


# ---------------------------------------------------------------------------
# Style × reference compatibility (pre-generation check)
# ---------------------------------------------------------------------------

# Empirical threshold: above this, the head dominates the frame so strongly
# that FLUX Kontext Pro must hallucinate the full body for sport / outdoor
# scenes. In production we observed consistent identity collapse at
# face_area_ratio > 0.35 for the yoga / beach / running style cluster.
FACE_TOO_TIGHT_FOR_BODY_THRESHOLD: float = 0.35


def check_style_reference_compat(
    face_area_ratio: float,
    mode: str,
    style_key: str,
) -> InputQualityIssue | None:
    """Return a soft warning issue if the (reference × style) combo is risky.

    This is a **bot-side** check run after the user has picked both a photo
    and a style — it cannot be done during the initial input_quality pass
    because we do not know the style yet. Intentionally returns a single
    optional ``warn``-severity issue rather than mutating a report: the
    caller decides how to surface it (inline keyboard with accept/reupload
    in the Telegram bot, banner on web, etc.).
    """
    # Local import to avoid circular import at module load:
    # src.prompts.image_gen imports src.services.style_catalog which — indirectly
    # through other modules — can re-enter input_quality during startup.
    from src.prompts.image_gen import STYLE_REGISTRY

    spec = STYLE_REGISTRY.get(mode, style_key)
    if spec is None or not spec.needs_full_body:
        return None

    if face_area_ratio <= FACE_TOO_TIGHT_FOR_BODY_THRESHOLD:
        return None

    return _issue(IssueCode.FACE_TOO_TIGHT_FOR_BODY_SHOT, "warn")
