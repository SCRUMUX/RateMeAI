from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

MAX_DIMENSION = 2048
MIN_DIMENSION = 100
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def validate_and_normalize(image_bytes: bytes) -> tuple[bytes, dict]:
    """Validate image, resize if needed, return normalized JPEG bytes and metadata."""
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
        logger.info("Resized image from %dx%d to %dx%d", width, height, *img.size)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)

    metadata = {
        "original_width": width,
        "original_height": height,
        "normalized_width": img.size[0],
        "normalized_height": img.size[1],
    }

    return buf.read(), metadata


def has_face_heuristic(image_bytes: bytes) -> bool:
    """Basic heuristic: check if image has reasonable dimensions for a portrait.
    Real face detection is delegated to the LLM vision call."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        aspect = w / h if h > 0 else 0
        return 0.3 < aspect < 3.0 and w >= MIN_DIMENSION and h >= MIN_DIMENSION
    except Exception:
        return False
