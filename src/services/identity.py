"""Lightweight face presence detection.

Historical context: this module used to compute ArcFace embeddings via
InsightFace for 1:1 identity verification. As part of the v1.10 privacy
overhaul (see docs/PRIVACY_AUDIT.md), all face-geometry extraction and
embedding persistence were removed — identity preservation is now
verified by the quality-gate VLM with two images in a single LLM call
(see src/services/quality_gates.py). What remains here is a minimal,
purely ephemeral *face presence* check used only for input validation.

Contract intentionally narrow:
- Input: JPEG/PNG bytes (already sanitized by validate_and_normalize).
- Output: bool (is there at least one face?).
- No feature vector is computed, stored, compared or returned.
"""
from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

_mp_detector = None
_mp_available: bool | None = None


def _get_detector():
    """Lazy-load MediaPipe FaceDetection (~5 MB model)."""
    global _mp_detector, _mp_available
    if _mp_available is False:
        return None
    if _mp_detector is not None:
        return _mp_detector
    try:
        import mediapipe as mp

        # model_selection=1: full-range model (handles faces further from camera)
        _mp_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.4
        )
        _mp_available = True
        logger.info("MediaPipe FaceDetection model loaded")
        return _mp_detector
    except Exception:
        _mp_available = False
        logger.info("MediaPipe not available — face detection disabled")
        return None


class IdentityService:
    """Face presence detection only. No embeddings, no comparison.

    Kept as a class for backward compatibility with callers that inject it
    as a dependency (executor, segmentation). All legacy methods
    (compute_embedding / compare / verify) have been removed.
    """

    def detect_face(self, image_bytes: bytes) -> bool:
        """Return True if the image contains at least one face."""
        detector = _get_detector()
        if detector is None:
            return False
        try:
            import numpy as np

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            arr = np.array(img)
            result = detector.process(arr)
            return bool(result.detections)
        except Exception:
            logger.debug("Face detection failed", exc_info=True)
            return False

    def face_bbox(self, image_bytes: bytes) -> tuple[int, int, int, int] | None:
        """Return (x1, y1, x2, y2) of the most confident face, or None."""
        detector = _get_detector()
        if detector is None:
            return None
        try:
            import numpy as np

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            arr = np.array(img)
            h, w = arr.shape[:2]
            result = detector.process(arr)
            if not result.detections:
                return None
            best = max(result.detections, key=lambda d: d.score[0])
            bbox = best.location_data.relative_bounding_box
            x1 = max(0, int(bbox.xmin * w))
            y1 = max(0, int(bbox.ymin * h))
            x2 = min(w, int((bbox.xmin + bbox.width) * w))
            y2 = min(h, int((bbox.ymin + bbox.height) * h))
            if x2 <= x1 or y2 <= y1:
                return None
            return x1, y1, x2, y2
        except Exception:
            logger.debug("Face bbox extraction failed", exc_info=True)
            return None
