"""Face cropping for identity-conditioned providers (v1.18).

Extracts a padded, square face crop from the user's uploaded photo to
feed PuLID's ``reference_images`` input. PuLID works best with a clean,
well-lit face crop of ~512-1024 px; it does not need the full body or
background.

We intentionally reuse the MediaPipe detector from
``src/services/input_quality.py`` (already loaded, already warmed up)
instead of adding a new dependency or model. This also means face_crop
has identical "face found?" semantics to the input quality gate — if
the gate passed, the crop will succeed.

Privacy: like the input gate, this module only reads a bounding box
and does not compute or store any face embedding. The crop is the same
identifiable data the user already uploaded — no new biometric
material is derived.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

from src.services.input_quality import _detect_faces

logger = logging.getLogger(__name__)


# Default padding around the detected face bbox, expressed as a fraction
# of the larger bbox dimension.
#
# v1.19 — dropped from 0.30 → 0.12. PuLID's ID adapter was trained on
# tight face crops (bbox + ~5–15% context) and dilutes the identity
# embedding when the crop contains half the hair, shoulders, and
# background clutter. 30% padding was a **direct** contributor to the
# "generic face" drift we saw on v1.18. 12% keeps forehead + chin but
# nothing else.
_DEFAULT_PADDING_RATIO = 0.12
# Target crop size fed to PuLID (square). 768 is large enough for the
# ID adapter's feature extractor and keeps the data URI base64 payload
# small (~280 KB at quality 92 vs ~500 KB at 1024). PuLID internally
# resizes to 336 px anyway.
_DEFAULT_CROP_SIZE = 768
# Minimum face bbox side in px after padding. Below this the crop is
# not useful to PuLID and we return ``None`` to let the router fall
# back to the scene-preserve edit model.
_MIN_USEFUL_FACE_SIDE_PX = 96


@dataclass
class FaceCropResult:
    """Outcome of a face-crop attempt.

    ``image_bytes`` is a JPEG blob ready to be base64-encoded into
    PuLID's ``reference_images[0].image_url``. ``reason`` is an empty
    string on success; otherwise it's a short machine-readable code
    for logs and metrics (see :data:`FaceCropReason`).
    """

    image_bytes: bytes | None
    reason: str = ""
    width: int = 0
    height: int = 0
    face_area_ratio: float = 0.0


class FaceCropReason:
    """Failure reason codes consumed by metrics/router."""

    OK = ""
    INVALID_IMAGE = "invalid_image"
    NO_FACE = "no_face"
    FACE_TOO_SMALL = "face_too_small"
    CROP_FAILED = "crop_failed"


def crop_face_for_pulid(
    image_bytes: bytes,
    *,
    padding_ratio: float = _DEFAULT_PADDING_RATIO,
    target_size: int = _DEFAULT_CROP_SIZE,
    min_face_side_px: int = _MIN_USEFUL_FACE_SIDE_PX,
    face_bbox: tuple[int, int, int, int] | None = None,
) -> FaceCropResult:
    """Return a padded square face crop or a failure reason.

    - Decodes ``image_bytes`` with PIL (RGB).
    - If ``face_bbox`` is supplied (v1.20 single-detect path), reuses it
      directly and skips MediaPipe. Otherwise runs MediaPipe face
      detection (via the existing input-quality detector) and picks the
      highest-confidence face.
    - Pads the bbox by ``padding_ratio`` and squares it up (symmetric
      padding on the narrow axis), clamping to image boundaries.
    - Resizes the crop to ``target_size × target_size`` with Lanczos.
    - Encodes as JPEG quality 92 and returns the bytes.

    On any failure (no face, degenerate bbox, detector unavailable)
    returns ``FaceCropResult(image_bytes=None, reason=<code>)`` — the
    caller should fall back to scene-preserve mode.
    """
    if not image_bytes:
        return FaceCropResult(None, reason=FaceCropReason.INVALID_IMAGE)

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        logger.debug("face_crop: cannot decode input (%s)", exc)
        return FaceCropResult(None, reason=FaceCropReason.INVALID_IMAGE)

    w, h = img.size
    if w < 64 or h < 64:
        return FaceCropResult(None, reason=FaceCropReason.INVALID_IMAGE)

    if face_bbox is not None:
        try:
            x1, y1, x2, y2 = [int(v) for v in face_bbox]
        except Exception:
            logger.debug("face_crop: malformed face_bbox=%r", face_bbox)
            return FaceCropResult(None, reason=FaceCropReason.NO_FACE)
    else:
        arr = np.array(img)
        faces = _detect_faces(arr)
        if not faces:
            return FaceCropResult(None, reason=FaceCropReason.NO_FACE)

        # Largest face by bbox area wins; det_score is a reasonable
        # secondary key (already sorted this way in input_quality).
        def _bbox_area(face) -> int:
            fx1, fy1, fx2, fy2 = face.bbox
            return max(0, fx2 - fx1) * max(0, fy2 - fy1)

        primary = max(
            faces,
            key=lambda f: (_bbox_area(f), float(f.det_score)),
        )
        x1, y1, x2, y2 = [int(v) for v in primary.bbox]
    fw = max(0, x2 - x1)
    fh = max(0, y2 - y1)
    if fw == 0 or fh == 0:
        return FaceCropResult(None, reason=FaceCropReason.NO_FACE)

    # Pad + square-up
    side = max(fw, fh)
    pad = int(round(side * float(padding_ratio)))
    side_padded = side + 2 * pad

    # Center of the face bbox — used to build a centered square.
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    half = side_padded // 2

    cx1 = cx - half
    cy1 = cy - half
    cx2 = cx + half
    cy2 = cy + half

    # Clamp to image boundaries while preserving the square aspect.
    shift_x = 0
    shift_y = 0
    if cx1 < 0:
        shift_x = -cx1
    elif cx2 > w:
        shift_x = w - cx2
    if cy1 < 0:
        shift_y = -cy1
    elif cy2 > h:
        shift_y = h - cy2
    cx1 += shift_x
    cx2 += shift_x
    cy1 += shift_y
    cy2 += shift_y
    # If the requested side still doesn't fit (tiny image), shrink it.
    final_w = min(cx2, w) - max(cx1, 0)
    final_h = min(cy2, h) - max(cy1, 0)
    if final_w < min_face_side_px or final_h < min_face_side_px:
        return FaceCropResult(
            None,
            reason=FaceCropReason.FACE_TOO_SMALL,
            face_area_ratio=(fw * fh) / float(max(1, w * h)),
        )

    try:
        crop = img.crop((max(0, cx1), max(0, cy1), min(w, cx2), min(h, cy2)))
        # Re-square in case the clamp shrank an axis.
        cw, ch = crop.size
        if cw != ch:
            target = min(cw, ch)
            left = (cw - target) // 2
            top = (ch - target) // 2
            crop = crop.crop((left, top, left + target, top + target))
        crop = crop.resize(
            (int(target_size), int(target_size)),
            Image.Resampling.LANCZOS,
        )
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=92, optimize=True)
        out = buf.getvalue()
    except Exception as exc:
        logger.debug("face_crop: crop/encode failed (%s)", exc)
        return FaceCropResult(None, reason=FaceCropReason.CROP_FAILED)

    face_area_ratio = (fw * fh) / float(max(1, w * h))
    logger.info(
        "face_crop OK: face_bbox=%dx%d face_area_ratio=%.3f out=%dx%d out_bytes=%d",
        fw,
        fh,
        face_area_ratio,
        target_size,
        target_size,
        len(out),
    )
    return FaceCropResult(
        image_bytes=out,
        reason=FaceCropReason.OK,
        width=int(target_size),
        height=int(target_size),
        face_area_ratio=round(face_area_ratio, 4),
    )


__all__ = [
    "FaceCropResult",
    "FaceCropReason",
    "crop_face_for_pulid",
]
