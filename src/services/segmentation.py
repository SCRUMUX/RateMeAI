"""Image segmentation service: face, body, background, and clothing masks.

Uses mediapipe SelfieSegmentation for body-vs-background and MediaPipe
FaceDetection (via ``IdentityService``) for the face bounding box. No
ArcFace embeddings, no face-recognition features — just bounding boxes.
Clothing mask is derived as body minus face region.
"""
from __future__ import annotations

import asyncio
import io
import logging

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

_selfie_seg = None


def _get_selfie_segmentor():
    global _selfie_seg
    if _selfie_seg is None:
        import mediapipe as mp
        _selfie_seg = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        logger.info("MediaPipe SelfieSegmentation model loaded")
    return _selfie_seg


def _image_to_array(image_bytes: bytes) -> tuple[np.ndarray, Image.Image]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img), img


def _face_bbox_mask(image_bytes: bytes, width: int, height: int, padding: float = 0.15) -> Image.Image | None:
    """Build a soft rectangular mask around the dominant face (MediaPipe)."""
    try:
        from src.services.identity import IdentityService
        bbox = IdentityService().face_bbox(image_bytes)
        if bbox is None:
            return None
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        pad_x, pad_y = int(bw * padding), int(bh * padding)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(width, x2 + pad_x)
        y2 = min(height, y2 + pad_y)

        mask = Image.new("L", (width, height), 0)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(mask)
        draw.rectangle([x1, y1, x2, y2], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(bw, bh) * 0.08))
        return mask
    except Exception:
        logger.exception("Face bbox mask extraction failed")
        return None


def _body_mask_sync(arr_rgb: np.ndarray, width: int, height: int) -> Image.Image:
    """Compute body (selfie) mask via mediapipe."""
    seg = _get_selfie_segmentor()
    result = seg.process(arr_rgb)
    raw = (result.segmentation_mask * 255).astype(np.uint8)
    mask = Image.fromarray(raw).resize((width, height), Image.BILINEAR)
    return mask


class SegmentationService:
    """Compute region masks for multi-pass pipeline editing."""

    async def segment(self, image_bytes: bytes) -> dict[str, Image.Image]:
        """Return masks: face, body, background, clothing (PIL mode 'L', 0-255)."""
        return await asyncio.to_thread(self._segment_sync, image_bytes)

    def _segment_sync(self, image_bytes: bytes) -> dict[str, Image.Image]:
        arr, img = _image_to_array(image_bytes)
        w, h = img.size

        body = _body_mask_sync(arr, w, h)
        bg = Image.fromarray(255 - np.array(body))

        face = _face_bbox_mask(image_bytes, w, h)
        if face is None:
            face = Image.new("L", (w, h), 0)

        body_arr = np.array(body).astype(np.int16)
        face_arr = np.array(face).astype(np.int16)
        clothing_arr = np.clip(body_arr - face_arr, 0, 255).astype(np.uint8)
        clothing = Image.fromarray(clothing_arr)

        return {
            "face": face,
            "body": body,
            "background": bg,
            "clothing": clothing,
            "full": Image.new("L", (w, h), 255),
        }
