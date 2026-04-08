"""Post-processing pipeline for photorealism.

Applies camera-authentic transformations to AI-generated images so they
resemble real photographs: film grain, vignette, chromatic aberration,
JPEG re-encode with realistic quality, and EXIF metadata injection.
"""
from __future__ import annotations

import asyncio
import io
import logging
import struct
import time
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Film grain  (luminance-dependent, mimics real sensor noise)
# ---------------------------------------------------------------------------

_GRAIN_ALPHA_RANGE = {
    "portra400": (0.025, 0.045),
    "default": (0.03, 0.05),
}


def _apply_film_grain(
    img: Image.Image,
    film_stock: str = "portra400",
    seed: int | None = None,
) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    rng = np.random.default_rng(seed)
    lo, hi = _GRAIN_ALPHA_RANGE.get(film_stock, _GRAIN_ALPHA_RANGE["default"])

    luminance = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    norm_lum = luminance / 255.0
    alpha_map = lo + (hi - lo) * (1.0 - norm_lum)

    noise = rng.standard_normal(arr.shape[:2]).astype(np.float32)
    for c in range(3):
        arr[..., c] += noise * alpha_map * 255.0

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


# ---------------------------------------------------------------------------
# Vignette  (radial darkening, mimics real lens light fall-off)
# ---------------------------------------------------------------------------

def _apply_vignette(img: Image.Image, strength: float = 0.08) -> Image.Image:
    w, h = img.size
    arr = np.array(img, dtype=np.float32)

    cx, cy = w / 2.0, h / 2.0
    max_dist = np.sqrt(cx ** 2 + cy ** 2)

    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / max_dist

    vignette = 1.0 - strength * (dist ** 2)
    vignette = np.clip(vignette, 0.0, 1.0)

    for c in range(3):
        arr[..., c] *= vignette

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


# ---------------------------------------------------------------------------
# Chromatic aberration  (subtle R/B channel shift at edges, ~0.5-1.0 px)
# ---------------------------------------------------------------------------

def _apply_chromatic_aberration(img: Image.Image, shift_px: float = 0.7) -> Image.Image:
    """Shift red channel outward and blue channel inward by `shift_px` at edges."""
    w, h = img.size
    if w < 200 or h < 200:
        return img

    arr = np.array(img)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    r_img = Image.fromarray(r)
    b_img = Image.fromarray(b)

    offset = max(1, round(shift_px))
    r_shifted = Image.new("L", (w, h), 0)
    r_shifted.paste(r_img, (-offset, -offset))
    b_shifted = Image.new("L", (w, h), 0)
    b_shifted.paste(b_img, (offset, offset))

    cx, cy = w / 2.0, h / 2.0
    max_dist = np.sqrt(cx ** 2 + cy ** 2)
    Y, X = np.ogrid[:h, :w]
    blend = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / max_dist
    blend = np.clip(blend * 1.5, 0.0, 1.0).astype(np.float32)

    r_arr = np.array(r_shifted, dtype=np.float32)
    b_arr = np.array(b_shifted, dtype=np.float32)
    r_final = (r.astype(np.float32) * (1 - blend) + r_arr * blend).astype(np.uint8)
    b_final = (b.astype(np.float32) * (1 - blend) + b_arr * blend).astype(np.uint8)

    result = np.stack([r_final, g, b_final], axis=-1)
    return Image.fromarray(result)


# ---------------------------------------------------------------------------
# JPEG re-encode  (matches real camera output pipelines)
# ---------------------------------------------------------------------------

def _jpeg_reencode(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# EXIF metadata injection  (lightweight, no piexif dependency)
# ---------------------------------------------------------------------------

def _build_minimal_exif(dt: datetime | None = None) -> bytes:
    """Build a minimal EXIF APP1 segment with camera make/model and datetime.

    Uses raw byte construction to avoid a piexif dependency.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    dt_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode("ascii") + b"\x00"

    def _ascii_tag(tag_id: int, value: bytes) -> bytes:
        return struct.pack(">HHI", tag_id, 2, len(value)) + (
            struct.pack(">I", 0) if len(value) <= 4 else struct.pack(">I", 0)
        )

    make = b"Canon\x00"
    model = b"Canon EOS R5\x00"

    ifd0_entries = []

    def _short(tag: int, val: int) -> bytes:
        return struct.pack(">HHI", tag, 3, 1) + struct.pack(">HH", val, 0)

    def _string_offset(tag: int, s: bytes, offset: int) -> tuple[bytes, bytes]:
        entry = struct.pack(">HHI", tag, 2, len(s)) + struct.pack(">I", offset)
        return entry, s

    header = b"Exif\x00\x00MM"
    header += struct.pack(">HI", 42, 8)

    try:
        entries: list[bytes] = []
        extra_data = b""
        num_tags = 3
        ifd_start = 8
        ifd_size = 2 + num_tags * 12 + 4
        data_offset = ifd_start + ifd_size

        e1, d1 = _string_offset(0x010F, make, data_offset)
        entries.append(e1)
        extra_data += d1
        data_offset += len(d1)

        e2, d2 = _string_offset(0x0110, model, data_offset)
        entries.append(e2)
        extra_data += d2
        data_offset += len(d2)

        e3, d3 = _string_offset(0x0132, dt_str, data_offset)
        entries.append(e3)
        extra_data += d3

        ifd = struct.pack(">H", num_tags)
        for e in entries:
            ifd += e
        ifd += struct.pack(">I", 0)

        tiff_body = header + ifd + extra_data
        app1 = b"\xFF\xE1" + struct.pack(">H", len(tiff_body) + 2) + tiff_body
        return app1
    except Exception:
        logger.debug("EXIF construction failed, skipping")
        return b""


def _inject_exif(jpeg_bytes: bytes) -> bytes:
    """Inject minimal EXIF into JPEG bytes, replacing any existing APP1."""
    exif_segment = _build_minimal_exif()
    if not exif_segment:
        return jpeg_bytes
    if jpeg_bytes[:2] != b"\xFF\xD8":
        return jpeg_bytes

    pos = 2
    while pos < len(jpeg_bytes) - 1:
        if jpeg_bytes[pos] != 0xFF:
            break
        marker = jpeg_bytes[pos + 1]
        if marker == 0xE1:
            seg_len = struct.unpack(">H", jpeg_bytes[pos + 2 : pos + 4])[0]
            return jpeg_bytes[:2] + exif_segment + jpeg_bytes[pos + 2 + seg_len :]
        if marker in (0xDA, 0x00):
            break
        if pos + 3 < len(jpeg_bytes):
            seg_len = struct.unpack(">H", jpeg_bytes[pos + 2 : pos + 4])[0]
            pos += 2 + seg_len
        else:
            break

    return jpeg_bytes[:2] + exif_segment + jpeg_bytes[2:]


# ---------------------------------------------------------------------------
# Face-region compositing  (Poisson blending fallback for identity failures)
# ---------------------------------------------------------------------------

async def composite_face_region(
    original_bytes: bytes,
    generated_bytes: bytes,
    identity_svc=None,
) -> tuple[bytes, float]:
    """Blend original face onto generated image for identity recovery.

    Uses alpha-blended face mask compositing (PIL-based, no OpenCV needed).
    Returns (composited_jpeg_bytes, new_identity_score).
    """
    return await asyncio.to_thread(
        _composite_face_sync, original_bytes, generated_bytes, identity_svc,
    )


def _composite_face_sync(
    original_bytes: bytes,
    generated_bytes: bytes,
    identity_svc=None,
) -> tuple[bytes, float]:
    from src.services.segmentation import _face_bbox_mask

    orig = Image.open(io.BytesIO(original_bytes)).convert("RGB")
    gen = Image.open(io.BytesIO(generated_bytes)).convert("RGB")

    if orig.size != gen.size:
        gen = gen.resize(orig.size, Image.LANCZOS)

    w, h = orig.size
    face_mask = _face_bbox_mask(original_bytes, w, h, padding=0.20)
    if face_mask is None:
        logger.warning("Face compositing: no face detected in original")
        return generated_bytes, 0.0

    face_mask = face_mask.filter(ImageFilter.GaussianBlur(radius=max(w, h) * 0.02))

    composited = Image.composite(orig, gen, face_mask)

    buf = io.BytesIO()
    composited.save(buf, format="JPEG", quality=92)
    result_bytes = buf.getvalue()

    score = 0.0
    if identity_svc:
        try:
            _, score = identity_svc.verify(original_bytes, result_bytes)
        except Exception:
            logger.debug("Identity check after compositing failed")

    return result_bytes, score


# ---------------------------------------------------------------------------
# Skin detail transfer  (high-frequency layer from original face region)
# ---------------------------------------------------------------------------

def _skin_detail_transfer(
    original: Image.Image,
    generated: Image.Image,
    face_mask: Image.Image,
    opacity: float = 0.35,
) -> Image.Image:
    """Transfer high-frequency skin details from original to generated image.

    Extracts fine details (pores, moles, freckles) via Gaussian decomposition
    and blends them onto the generated face region.
    """
    if original.size != generated.size:
        original = original.resize(generated.size, Image.LANCZOS)
    if face_mask.size != generated.size:
        face_mask = face_mask.resize(generated.size, Image.BILINEAR)

    blur_radius = max(generated.size) * 0.01
    blur_radius = max(3, int(blur_radius))

    orig_arr = np.array(original, dtype=np.float32)
    orig_blur = np.array(original.filter(ImageFilter.GaussianBlur(radius=blur_radius)), dtype=np.float32)
    high_freq = orig_arr - orig_blur

    gen_arr = np.array(generated, dtype=np.float32)
    mask_arr = np.array(face_mask, dtype=np.float32) / 255.0
    mask_3d = np.stack([mask_arr] * 3, axis=-1)

    blended = gen_arr + high_freq * mask_3d * opacity
    blended = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(blended)


# ---------------------------------------------------------------------------
# Film color science  (Portra 400 tone curve)
# ---------------------------------------------------------------------------

def _portra400_color_grade(img: Image.Image) -> Image.Image:
    """Apply Kodak Portra 400-inspired color grading.

    - Highlight compression (soft shoulder for skin tones)
    - Warm shift in shadows
    - Green desaturation in midtones
    """
    arr = np.array(img, dtype=np.float32) / 255.0

    def _soft_shoulder(x: np.ndarray, knee: float = 0.75) -> np.ndarray:
        mask = x > knee
        linear = x.copy()
        excess = x[mask] - knee
        linear[mask] = knee + excess * 0.6
        return np.clip(linear, 0.0, 1.0)

    arr[..., 0] = _soft_shoulder(arr[..., 0], 0.72)
    arr[..., 1] = _soft_shoulder(arr[..., 1], 0.75)
    arr[..., 2] = _soft_shoulder(arr[..., 2], 0.78)

    luminance = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    shadow_mask = np.clip(1.0 - luminance * 2.0, 0.0, 1.0)
    arr[..., 0] += shadow_mask * 0.012
    arr[..., 1] += shadow_mask * 0.006

    mid_mask = 1.0 - np.abs(luminance - 0.5) * 2.0
    mid_mask = np.clip(mid_mask, 0.0, 1.0)
    arr[..., 1] -= mid_mask * 0.008

    arr = np.clip(arr, 0.0, 1.0)
    return Image.fromarray((arr * 255).astype(np.uint8))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def postprocess_for_realism(
    image_bytes: bytes,
    original_bytes: bytes | None = None,
    film_stock: str = "portra400",
    enable_color_grade: bool = True,
    enable_skin_transfer: bool = False,
    jpeg_quality: int = 90,
) -> bytes:
    """Full post-processing pipeline. Runs CPU-bound work in a thread."""
    return await asyncio.to_thread(
        _postprocess_sync,
        image_bytes, original_bytes, film_stock,
        enable_color_grade, enable_skin_transfer, jpeg_quality,
    )


def _postprocess_sync(
    image_bytes: bytes,
    original_bytes: bytes | None,
    film_stock: str,
    enable_color_grade: bool,
    enable_skin_transfer: bool,
    jpeg_quality: int,
) -> bytes:
    t0 = time.monotonic()
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        logger.debug("Post-processing: input is not a valid image, returning as-is")
        return image_bytes

    seed = hash(image_bytes[:256]) & 0xFFFFFFFF

    if enable_color_grade:
        img = _portra400_color_grade(img)

    if enable_skin_transfer and original_bytes:
        try:
            from src.services.segmentation import _face_bbox_mask
            orig = Image.open(io.BytesIO(original_bytes)).convert("RGB")
            face_mask = _face_bbox_mask(original_bytes, img.size[0], img.size[1], padding=0.15)
            if face_mask is not None:
                img = _skin_detail_transfer(orig, img, face_mask, opacity=0.35)
        except Exception:
            logger.debug("Skin detail transfer failed, skipping")

    img = _apply_film_grain(img, film_stock=film_stock, seed=seed)
    img = _apply_vignette(img, strength=0.08)
    img = _apply_chromatic_aberration(img, shift_px=0.7)

    jpeg = _jpeg_reencode(img, quality=jpeg_quality)
    jpeg = _inject_exif(jpeg)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info("Post-processing completed in %.1fms (%d bytes)", elapsed, len(jpeg))
    return jpeg
