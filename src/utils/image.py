from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

MAX_DIMENSION = 2048
MIN_DIMENSION = 100
OPTIMAL_MIN_DIMENSION = 1024
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def validate_and_normalize(image_bytes: bytes) -> tuple[bytes, dict]:
    """Validate image, resize if needed, return normalized JPEG bytes and metadata.

    Ensures the image is at least OPTIMAL_MIN_DIMENSION on the longest side
    for best results with image generation APIs, and caps at MAX_DIMENSION.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")

    if img.format and img.format.upper() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {img.format}")

    width, height = img.size
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ValueError(f"Image too small: {width}x{height}. Minimum {MIN_DIMENSION}x{MIN_DIMENSION}.")

    img = img.convert("RGB")

    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        logger.info("Downscaled image from %dx%d to %dx%d", width, height, *img.size)

    long_side = max(img.size)
    if long_side < OPTIMAL_MIN_DIMENSION:
        scale = OPTIMAL_MIN_DIMENSION / long_side
        new_w = round(img.size[0] * scale)
        new_h = round(img.size[1] * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info("Upscaled small image from %dx%d to %dx%d for better generation quality",
                     width, height, new_w, new_h)

    # Privacy: explicitly drop EXIF/ICC/XMP/GPS and any other ancillary metadata.
    # PIL's re-encode would implicitly lose most of them, but we assert it here
    # so future PIL versions or kwargs cannot regress the invariant.
    img.info = {}
    if "exif" in img.info:
        del img.info["exif"]

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, exif=b"", icc_profile=None)
    buf.seek(0)

    metadata = {
        "original_width": width,
        "original_height": height,
        "normalized_width": img.size[0],
        "normalized_height": img.size[1],
    }

    return buf.read(), metadata


def estimate_blur_score(image_bytes: bytes) -> float:
    """Estimate image sharpness via Laplacian variance. Lower = blurrier.

    Returns variance of the Laplacian. Typical threshold: < 100 is blurry.
    Returns -1.0 if computation fails (caller should skip the check).
    """
    try:
        import numpy as np

        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        arr = np.array(img, dtype=np.float64)
        # 3x3 Laplacian kernel convolution via numpy
        laplacian = (
            -arr[:-2, 1:-1] - arr[2:, 1:-1]
            - arr[1:-1, :-2] - arr[1:-1, 2:]
            + 4 * arr[1:-1, 1:-1]
        )
        variance = float(np.var(laplacian))
        logger.debug("Blur score (Laplacian variance): %.1f", variance)
        return variance
    except Exception:
        logger.debug("Blur estimation failed, skipping check")
        return -1.0


def has_face_heuristic(image_bytes: bytes) -> bool:
    """Detect a face using the lightweight MediaPipe detector.

    Falls back to an aspect-ratio heuristic when MediaPipe is unavailable.
    No feature vectors or identity-grade embeddings are produced here —
    this is purely a presence check used for input validation.
    """
    try:
        from src.services.identity import IdentityService
        return IdentityService().detect_face(image_bytes)
    except ImportError:
        pass
    except Exception:
        logger.debug("MediaPipe detection failed, falling back to heuristic")

    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        aspect = w / h if h > 0 else 0
        return 0.3 < aspect < 3.0 and w >= MIN_DIMENSION and h >= MIN_DIMENSION
    except Exception:
        return False
